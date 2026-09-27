"""Configured fixed-size lookups over the precomputed product metrics view."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict

from config.settings import load_agent_settings
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


_RANKING_SETTINGS = load_agent_settings().rankings
BOTTOM_RATE_RESULT_LIMIT = _RANKING_SETTINGS.bottom_rate_result_limit

LESS_LIKE_SQL = f"""
SELECT
    page_or_product,
    like_rate
FROM public.v_product_metrics
WHERE like_rate IS NOT NULL
ORDER BY like_rate ASC
LIMIT {BOTTOM_RATE_RESULT_LIMIT}
"""

LESS_PURCHASE_SQL = f"""
SELECT
    page_or_product,
    purchase_rate
FROM public.v_product_metrics
WHERE purchase_rate IS NOT NULL
ORDER BY purchase_rate ASC
LIMIT {BOTTOM_RATE_RESULT_LIMIT}
"""

MetricName = Literal["like_rate", "purchase_rate"]
AgentName = Literal["finance", "operations"]


class NoToolInput(BaseModel):
    """Declare that configured fixed-ranking tools accept no model arguments."""

    model_config = ConfigDict(extra="forbid")


def _json_number(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _query_metric_ranking(
    statement: str,
    metric: MetricName,
) -> list[dict[str, Any]]:
    """Execute one fixed view query and return names with the ranking metric."""

    with connect_readonly() as connection:
        with connection.cursor() as cursor:
            set_readonly_guards(cursor)
            cursor.execute(statement)
            rows = cursor.fetchall()
    return [
        {
            "product_name": str(row[0]),
            metric: _json_number(row[1]),
        }
        for row in rows
    ]


def _active_agent(config: RunnableConfig, default: AgentName) -> AgentName:
    configurable = config.get("configurable")
    if isinstance(configurable, dict):
        agent_name = configurable.get("agent_name")
        if agent_name in {"finance", "operations"}:
            return agent_name
    return default


def _evidence_artifact(
    *,
    agent_name: AgentName,
    tool_name: str,
    metric: MetricName,
    statement: str,
    row_count: int,
) -> dict[str, Any]:
    query_id = sha256(
        json.dumps(
            {"agent": agent_name, "tool": tool_name, "sql": statement},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    citation = f"[db:{agent_name}:{query_id}]"
    source = {
        "type": "database_query",
        "filename": "PostgreSQL · v_product_metrics",
        "citation": citation,
        "query_id": query_id,
        "tables": ["v_product_metrics"],
        "row_count": row_count,
    }
    return {
        "success": True,
        "result_status": "ok" if row_count else "empty_result",
        "agent": agent_name,
        "tool": tool_name,
        "metric": metric,
        "row_count": row_count,
        "citation": citation,
        "sources": [source],
    }


async def _run_bottom_ten(
    *,
    tool_name: str,
    metric: MetricName,
    statement: str,
    agent_name: AgentName,
) -> tuple[str, dict[str, Any]]:
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        source_view="v_product_metrics",
        metric=metric,
        limit=BOTTOM_RATE_RESULT_LIMIT,
    )
    try:
        ranking = await asyncio.to_thread(_query_metric_ranking, statement, metric)
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
            f"{tool_name} could not query the product metrics view."
        ) from error

    artifact = _evidence_artifact(
        agent_name=agent_name,
        tool_name=tool_name,
        metric=metric,
        statement=statement,
        row_count=len(ranking),
    )
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=True,
        result_status=artifact["result_status"],
        row_count=len(ranking),
    )
    return json.dumps(ranking, ensure_ascii=False), artifact


@tool(args_schema=NoToolInput, response_format="content_and_artifact")
async def check_less_like(config: RunnableConfig) -> tuple[str, dict[str, Any]]:
    """Return the configured number of lowest non-null precomputed like rates."""

    return await _run_bottom_ten(
        tool_name="check_less_like",
        metric="like_rate",
        statement=LESS_LIKE_SQL,
        agent_name=_active_agent(config, "operations"),
    )


@tool(args_schema=NoToolInput, response_format="content_and_artifact")
async def check_less_purchase(config: RunnableConfig) -> tuple[str, dict[str, Any]]:
    """Return the configured number of lowest non-null precomputed purchase rates."""

    return await _run_bottom_ten(
        tool_name="check_less_purchase",
        metric="purchase_rate",
        statement=LESS_PURCHASE_SQL,
        agent_name=_active_agent(config, "operations"),
    )


__all__ = [
    "LESS_LIKE_SQL",
    "LESS_PURCHASE_SQL",
    "BOTTOM_RATE_RESULT_LIMIT",
    "NoToolInput",
    "check_less_like",
    "check_less_purchase",
]
