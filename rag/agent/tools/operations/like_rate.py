"""Fixed-query Operations tool for product view-to-like conversion."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from observability import logger
from rag.agent.tools.common.products import canonical_product_name_error
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


LIKE_RATE_SQL = """
SELECT
    page_or_product,
    COUNT(*) FILTER (WHERE interaction_type = 'product_view') AS product_views,
    COUNT(*) FILTER (WHERE interaction_type = 'wishlist_add') AS wishlist_adds,
    COUNT(*) FILTER (WHERE interaction_type = 'add_to_cart') AS add_to_carts,
    ROUND(
        COUNT(*) FILTER (
            WHERE interaction_type IN ('wishlist_add', 'add_to_cart')
        )::numeric
        / NULLIF(
            COUNT(*) FILTER (WHERE interaction_type = 'product_view'),
            0
        ),
        4
    ) AS like_rate
FROM public.interactions
WHERE page_or_product = %(product_name)s::text
GROUP BY page_or_product
"""

LikeRateStatus = Literal[
    "ok",
    "empty_result",
    "undefined_rate",
    "query_failed",
]


class CheckLikeRateInput(BaseModel):
    """Validated exact product-name input."""

    product_name: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "An exact canonical product_name, normally returned by find_real_name."
        ),
    )


def _query_like_rate(product_name: str) -> dict[str, Any] | None:
    """Run the fixed aggregate query inside a read-only transaction."""

    with connect_readonly() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            set_readonly_guards(cursor)
            cursor.execute(LIKE_RATE_SQL, {"product_name": product_name})
            row = cursor.fetchone()
    return dict(row) if row is not None else None


def _query_identity(product_name: str) -> tuple[str, str]:
    fingerprint = sha256(
        json.dumps(
            {
                "tool": "check_like_rate",
                "sql": LIKE_RATE_SQL,
                "product_name": product_name,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return fingerprint, f"[db:operations:{fingerprint}]"


def _success_payload(
    product_name: str,
    row: dict[str, Any] | None,
) -> dict[str, Any]:
    query_id, citation = _query_identity(product_name)
    source = {
        "type": "database_query",
        "filename": "PostgreSQL · interactions",
        "citation": citation,
        "query_id": query_id,
        "tables": ["interactions"],
        "row_count": 0 if row is None else 1,
    }
    if row is None:
        return {
            "success": True,
            "result_status": "empty_result",
            "agent": "operations",
            "tool": "check_like_rate",
            "product_name": product_name,
            "like_rate": None,
            "product_views": 0,
            "wishlist_adds": 0,
            "add_to_carts": 0,
            "row_count": 0,
            "citation": citation,
            "sources": [source],
        }

    raw_rate = row.get("like_rate")
    like_rate = (
        float(raw_rate)
        if isinstance(raw_rate, (Decimal, int, float))
        else None
    )
    result_status: LikeRateStatus = (
        "ok" if like_rate is not None else "undefined_rate"
    )
    return {
        "success": True,
        "result_status": result_status,
        "agent": "operations",
        "tool": "check_like_rate",
        "product_name": str(row["page_or_product"]),
        "like_rate": like_rate,
        "product_views": int(row["product_views"]),
        "wishlist_adds": int(row["wishlist_adds"]),
        "add_to_carts": int(row["add_to_carts"]),
        "row_count": 1,
        "citation": citation,
        "sources": [source],
    }


@tool(args_schema=CheckLikeRateInput)
async def check_like_rate(product_name: str, config: RunnableConfig) -> str:
    """Return product like events divided by product-view events."""

    tool_name = "check_like_rate"
    product_error = canonical_product_name_error(config, product_name)
    if product_error:
        return json.dumps(
            {
                "success": False,
                "result_status": "unverified_product_name",
                "agent": "operations",
                "tool": tool_name,
                "product_name": product_name,
                "like_rate": None,
                "error_type": product_error,
                "error": (
                    "The product name was not returned by find_real_name. "
                    "Do not query a guessed or invented product name."
                ),
                "row_count": 0,
                "sources": [],
            },
            ensure_ascii=False,
        )
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        product_name_length=len(product_name),
    )
    try:
        row = await asyncio.to_thread(_query_like_rate, product_name)
        payload = _success_payload(product_name, row)
    except Exception as error:
        logger.exception(
            "tool.failed",
            error,
            component="tool",
            tool_name=tool_name,
        )
        payload = {
            "success": False,
            "result_status": "query_failed",
            "agent": "operations",
            "tool": tool_name,
            "product_name": product_name,
            "like_rate": None,
            "error_type": "database_error",
            "error": "The like-rate query could not be completed.",
            "row_count": 0,
            "sources": [],
        }

    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=payload["success"],
        result_status=payload["result_status"],
        row_count=payload["row_count"],
    )
    return json.dumps(payload, ensure_ascii=False, default=str)


__all__ = [
    "CheckLikeRateInput",
    "LIKE_RATE_SQL",
    "LikeRateStatus",
    "check_like_rate",
]
