"""Fixed-query product interaction-duration rankings for Operations."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any

from langchain_core.tools import tool

from observability import logger
from rag.agent.tools.common.product_metrics import NoToolInput
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


MOST_INTERACT_SQL = """
WITH stats AS (
    SELECT
        i.page_or_product,
        SUM(i.duration) AS total_duration,
        ROUND(AVG(i.duration), 2) AS avg_duration,
        COUNT(*) AS interaction_cnt
    FROM public.interactions i
    WHERE i.page_or_product IS NOT NULL
      AND i.duration IS NOT NULL
      AND i.page_or_product IN (
          SELECT product_name
          FROM public.products
      )
    GROUP BY i.page_or_product
    HAVING COUNT(*) >= 20
),
ranked AS (
    SELECT
        page_or_product,
        total_duration,
        avg_duration,
        interaction_cnt,
        RANK() OVER (ORDER BY total_duration DESC) AS rank_total,
        RANK() OVER (ORDER BY avg_duration DESC) AS rank_avg,
        ROUND(
            (
                RANK() OVER (ORDER BY total_duration DESC)
                + RANK() OVER (ORDER BY avg_duration DESC)
            ) / 2.0,
            1
        ) AS rank_combo
    FROM stats
)
SELECT
    page_or_product,
    total_duration,
    avg_duration,
    interaction_cnt,
    rank_total,
    rank_avg,
    rank_combo
FROM ranked
ORDER BY rank_combo ASC, total_duration DESC
LIMIT 10
"""


def _json_number(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _query_most_interacted_products() -> list[dict[str, Any]]:
    """Execute the fixed query and return products with their ranking inputs."""

    with connect_readonly() as connection:
        with connection.cursor() as cursor:
            set_readonly_guards(cursor)
            cursor.execute(MOST_INTERACT_SQL)
            rows = cursor.fetchall()
    return [
        {
            "product_name": str(row[0]),
            "total_duration": _json_number(row[1]),
            "avg_duration": _json_number(row[2]),
            "interaction_count": int(row[3]),
            "rank_total": int(row[4]),
            "rank_avg": int(row[5]),
            "rank_combo": _json_number(row[6]),
        }
        for row in rows
    ]


def _evidence_artifact(row_count: int) -> dict[str, Any]:
    query_id = sha256(
        json.dumps(
            {
                "agent": "operations",
                "tool": "check_most_interact",
                "sql": MOST_INTERACT_SQL,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    citation = f"[db:operations:{query_id}]"
    source = {
        "type": "database_query",
        "filename": "PostgreSQL · interactions, products",
        "citation": citation,
        "query_id": query_id,
        "tables": ["interactions", "products"],
        "row_count": row_count,
    }
    return {
        "success": True,
        "result_status": "ok" if row_count else "empty_result",
        "agent": "operations",
        "tool": "check_most_interact",
        "metric": "interaction_duration_rank_combo",
        "minimum_interactions": 20,
        "row_count": row_count,
        "citation": citation,
        "sources": [source],
    }


@tool(args_schema=NoToolInput, response_format="content_and_artifact")
async def check_most_interact() -> tuple[str, dict[str, Any]]:
    """Return the top 10 products by combined total and average interaction duration rank."""

    tool_name = "check_most_interact"
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        minimum_interactions=20,
        limit=10,
    )
    try:
        ranking = await asyncio.to_thread(_query_most_interacted_products)
    except Exception as error:
        logger.exception(
            "tool.failed",
            error,
            component="tool",
            tool_name=tool_name,
        )
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            success=False,
            result_status="query_failed",
            row_count=0,
        )
        raise RuntimeError(
            "check_most_interact could not query product interaction rankings."
        ) from error

    artifact = _evidence_artifact(len(ranking))
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=True,
        result_status=artifact["result_status"],
        row_count=len(ranking),
    )
    return json.dumps(ranking, ensure_ascii=False), artifact


__all__ = ["MOST_INTERACT_SQL", "check_most_interact"]
