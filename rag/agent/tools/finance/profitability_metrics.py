"""Fixed-query Finance tools for net sales, gross profit, and gross margin."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, model_validator

from observability import logger
from rag.agent.tools.common.products import canonical_product_name_error
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards
from rag.agent.tools.finance.skill_loader import selected_finance_skills


NET_SALES_SQL = """
WITH completed_refunds AS (
    SELECT
        transaction_id,
        SUM(refund_amount) AS completed_refund_amount,
        BOOL_OR(is_synthetic) AS has_synthetic_refund
    FROM public.returns_refunds
    WHERE refund_status = 'completed'
    GROUP BY transaction_id
), scoped_transactions AS (
    SELECT
        t.transaction_id,
        t.gross_sales,
        t.discount_amount,
        t.net_sales,
        COALESCE(r.completed_refund_amount, 0) AS completed_refund_amount,
        COALESCE(r.has_synthetic_refund, FALSE) AS has_synthetic_refund
    FROM public.transactions t
    LEFT JOIN completed_refunds r ON r.transaction_id = t.transaction_id
    WHERE (%(start_date)s::date IS NULL OR t.transaction_date >= %(start_date)s::date)
      AND (%(end_date)s::date IS NULL OR t.transaction_date < %(end_date)s::date)
      AND (%(product_name)s::text IS NULL OR LOWER(t.product_name) = LOWER(%(product_name)s::text))
      AND (%(product_category)s::text IS NULL OR LOWER(t.product_category) = LOWER(%(product_category)s::text))
      AND (%(store_location)s::text IS NULL OR LOWER(t.store_location) = LOWER(%(store_location)s::text))
      AND (%(payment_method)s::text IS NULL OR LOWER(t.payment_method) = LOWER(%(payment_method)s::text))
)
SELECT
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (WHERE completed_refund_amount > 0)
        AS completed_refund_transaction_count,
    COUNT(*) FILTER (WHERE has_synthetic_refund IS TRUE)
        AS synthetic_refund_transaction_count,
    ROUND(COALESCE(SUM(gross_sales), 0), 2) AS gross_sales,
    ROUND(COALESCE(SUM(discount_amount), 0), 2) AS discount_amount,
    ROUND(COALESCE(SUM(net_sales), 0), 2) AS net_sales_before_refunds,
    ROUND(COALESCE(SUM(completed_refund_amount), 0), 2) AS completed_refunds,
    ROUND(
        COALESCE(SUM(net_sales), 0)
        - COALESCE(SUM(completed_refund_amount), 0),
        2
    ) AS net_sales
FROM scoped_transactions
"""


GROSS_PROFIT_MARGIN_SQL = """
WITH completed_refunds AS (
    SELECT
        transaction_id,
        SUM(refund_amount) AS completed_refund_amount,
        BOOL_OR(is_synthetic) AS has_synthetic_refund
    FROM public.returns_refunds
    WHERE refund_status = 'completed'
    GROUP BY transaction_id
), scoped_transactions AS (
    SELECT
        t.transaction_id,
        t.quantity,
        t.net_sales,
        COALESCE(r.completed_refund_amount, 0) AS completed_refund_amount,
        COALESCE(r.has_synthetic_refund, FALSE) AS has_synthetic_refund,
        p.unit_cost,
        p.is_cost_synthetic
    FROM public.transactions t
    LEFT JOIN completed_refunds r ON r.transaction_id = t.transaction_id
    LEFT JOIN public.products p ON p.product_id = t.product_id
    WHERE (%(start_date)s::date IS NULL OR t.transaction_date >= %(start_date)s::date)
      AND (%(end_date)s::date IS NULL OR t.transaction_date < %(end_date)s::date)
      AND (%(product_name)s::text IS NULL OR LOWER(t.product_name) = LOWER(%(product_name)s::text))
      AND (%(product_category)s::text IS NULL OR LOWER(t.product_category) = LOWER(%(product_category)s::text))
      AND (%(store_location)s::text IS NULL OR LOWER(t.store_location) = LOWER(%(store_location)s::text))
      AND (%(payment_method)s::text IS NULL OR LOWER(t.payment_method) = LOWER(%(payment_method)s::text))
)
SELECT
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (WHERE completed_refund_amount > 0)
        AS completed_refund_transaction_count,
    COUNT(*) FILTER (WHERE has_synthetic_refund IS TRUE)
        AS synthetic_refund_transaction_count,
    COUNT(*) FILTER (WHERE unit_cost IS NOT NULL) AS costed_transaction_count,
    COUNT(*) FILTER (WHERE unit_cost IS NULL) AS missing_cost_transaction_count,
    COUNT(*) FILTER (WHERE is_cost_synthetic IS TRUE) AS synthetic_cost_transaction_count,
    ROUND(COALESCE(SUM(net_sales), 0), 2) AS net_sales_before_refunds,
    ROUND(COALESCE(SUM(completed_refund_amount), 0), 2) AS completed_refunds,
    ROUND(
        COALESCE(SUM(net_sales - completed_refund_amount), 0),
        2
    ) AS recognized_revenue,
    ROUND(
        COALESCE(
            SUM(net_sales - completed_refund_amount)
                FILTER (WHERE unit_cost IS NOT NULL),
            0
        ),
        2
    ) AS costed_recognized_revenue,
    ROUND(
        COALESCE(SUM(quantity * unit_cost) FILTER (WHERE unit_cost IS NOT NULL), 0),
        2
    ) AS cost_of_goods_sold,
    ROUND(
        COALESCE(
            SUM(net_sales - completed_refund_amount - quantity * unit_cost)
                FILTER (WHERE unit_cost IS NOT NULL),
            0
        ),
        2
    ) AS gross_profit,
    ROUND(
        100 * COALESCE(
            SUM(net_sales - completed_refund_amount - quantity * unit_cost)
                FILTER (WHERE unit_cost IS NOT NULL),
            0
        ) / NULLIF(
            SUM(net_sales - completed_refund_amount)
                FILTER (WHERE unit_cost IS NOT NULL),
            0
        ),
        2
    ) AS gross_margin_percent,
    ROUND(
        100 * COALESCE(
            SUM(net_sales - completed_refund_amount)
                FILTER (WHERE unit_cost IS NOT NULL),
            0
        ) / NULLIF(SUM(net_sales - completed_refund_amount), 0),
        2
    ) AS cost_coverage_percent
FROM scoped_transactions
"""


FinanceMetricName = Literal["net_sales", "gross_profit", "gross_margin"]
REQUIRED_SKILL = {
    "net_sales": "net_sales",
    "gross_profit": "gross_profit_margin",
    "gross_margin": "gross_profit_margin",
}


class FinanceMetricInput(BaseModel):
    """Validated scope shared by both fixed Finance calculations."""

    start_date: date | None = Field(
        default=None,
        description="Optional inclusive transaction-date lower bound.",
    )
    end_date: date | None = Field(
        default=None,
        description="Optional exclusive transaction-date upper bound.",
    )
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    product_category: str | None = Field(default=None, min_length=1, max_length=200)
    store_location: str | None = Field(default=None, min_length=1, max_length=200)
    payment_method: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_dates(self) -> "FinanceMetricInput":
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must be earlier than end_date")
        return self


def _runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("finance_metric_runtime_state")
    if not isinstance(state, dict):
        state = {"calls": {}, "in_flight": []}
        configurable["finance_metric_runtime_state"] = state
    state.setdefault("calls", {})
    state.setdefault("in_flight", [])
    return state


def _claim_call(config: RunnableConfig, metric: FinanceMetricName) -> str:
    state = _runtime_state(config)
    calls = state["calls"]
    in_flight = state["in_flight"]
    if metric in in_flight:
        return "concurrent_query_blocked"
    if int(calls.get(metric, 0)) >= 1:
        return "attempt_limit"
    calls[metric] = 1
    in_flight.append(metric)
    return "permitted"


def _finish_call(config: RunnableConfig, metric: FinanceMetricName) -> None:
    state = _runtime_state(config)
    state["in_flight"] = [item for item in state["in_flight"] if item != metric]


def _parameters(inputs: FinanceMetricInput) -> dict[str, Any]:
    return inputs.model_dump()


def _query_metric(statement: str, inputs: FinanceMetricInput) -> dict[str, Any]:
    with connect_readonly() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            set_readonly_guards(cursor)
            cursor.execute(statement, _parameters(inputs))
            row = cursor.fetchone()
    return dict(row) if row is not None else {}


def _json_value(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _json_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in row.items()}


def _query_identity(
    tool_name: str,
    statement: str,
    inputs: FinanceMetricInput,
) -> tuple[str, str]:
    query_id = sha256(
        json.dumps(
            {
                "agent": "finance",
                "tool": tool_name,
                "sql": statement,
                "parameters": inputs.model_dump(mode="json"),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return query_id, f"[db:finance:{query_id}]"


def _blocked_payload(tool_name: str, error_type: str) -> str:
    errors = {
        "skill_not_loaded": (
            "Load the matching Finance skill before calling this dedicated tool."
        ),
        "concurrent_query_blocked": (
            "Another call for this Finance metric is already running."
        ),
        "attempt_limit": "This Finance metric tool may be called only once per run.",
        "unverified_canonical_product": (
            "The product name was not returned by find_real_name."
        ),
    }
    return json.dumps(
        {
            "success": False,
            "agent": "finance",
            "tool": tool_name,
            "error_type": error_type,
            "error": errors[error_type],
            "retryable": error_type == "skill_not_loaded",
            "sources": [],
        },
        ensure_ascii=False,
    )


async def _run_metric(
    *,
    tool_name: str,
    metric: FinanceMetricName,
    statement: str,
    tables: list[str],
    inputs: FinanceMetricInput,
    config: RunnableConfig,
) -> str:
    if REQUIRED_SKILL[metric] not in selected_finance_skills(config):
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type="skill_not_loaded",
        )
        return _blocked_payload(tool_name, "skill_not_loaded")
    if inputs.product_name:
        product_error = canonical_product_name_error(config, inputs.product_name)
        if product_error:
            logger.tool_event(
                status="completed",
                tool_name=tool_name,
                success=False,
                error_type="unverified_canonical_product",
            )
            return _blocked_payload(tool_name, "unverified_canonical_product")
    claim_status = _claim_call(config, metric)
    if claim_status != "permitted":
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type=claim_status,
        )
        return _blocked_payload(tool_name, claim_status)

    started_at = perf_counter()
    filters = inputs.model_dump(mode="json")
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        metric=metric,
        filtered=any(value is not None for value in filters.values()),
    )
    try:
        result = _json_row(await asyncio.to_thread(_query_metric, statement, inputs))
        query_id, citation = _query_identity(tool_name, statement, inputs)
        transaction_count = int(result.get("transaction_count") or 0)
        payload = {
            "success": True,
            "result_status": "ok" if transaction_count else "empty_result",
            "agent": "finance",
            "tool": tool_name,
            "metric": metric,
            "filters": filters,
            "result": result,
            "row_count": 1,
            "citation": citation,
            "sources": [
                {
                    "type": "database_query",
                    "filename": "PostgreSQL · " + ", ".join(tables),
                    "citation": citation,
                    "query_id": query_id,
                    "tables": tables,
                    "row_count": 1,
                }
            ],
        }
    except Exception as error:
        logger.exception("tool.failed", error, component="tool", tool_name=tool_name)
        payload = {
            "success": False,
            "result_status": "query_failed",
            "agent": "finance",
            "tool": tool_name,
            "metric": metric,
            "filters": filters,
            "error_type": "database_error",
            "error": f"The fixed {metric} query could not be completed.",
            "row_count": 0,
            "sources": [],
        }
    finally:
        _finish_call(config, metric)

    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=payload["success"],
        result_status=payload["result_status"],
        transaction_count=int(payload.get("result", {}).get("transaction_count") or 0),
        error_type=payload.get("error_type"),
    )
    return json.dumps(payload, ensure_ascii=False, default=str)


@tool(args_schema=FinanceMetricInput)
async def calculate_net_sales(
    config: RunnableConfig,
    start_date: date | None = None,
    end_date: date | None = None,
    product_name: str | None = None,
    product_category: str | None = None,
    store_location: str | None = None,
    payment_method: str | None = None,
) -> str:
    """Calculate refund-adjusted net sales with one fixed read-only query."""

    return await _run_metric(
        tool_name="calculate_net_sales",
        metric="net_sales",
        statement=NET_SALES_SQL,
        tables=["transactions", "returns_refunds"],
        inputs=FinanceMetricInput(
            start_date=start_date,
            end_date=end_date,
            product_name=product_name,
            product_category=product_category,
            store_location=store_location,
            payment_method=payment_method,
        ),
        config=config,
    )


@tool(args_schema=FinanceMetricInput)
async def calculate_gross_profit(
    config: RunnableConfig,
    start_date: date | None = None,
    end_date: date | None = None,
    product_name: str | None = None,
    product_category: str | None = None,
    store_location: str | None = None,
    payment_method: str | None = None,
) -> str:
    """Calculate gross profit from recorded sales, refunds, and product cost."""

    return await _run_metric(
        tool_name="calculate_gross_profit",
        metric="gross_profit",
        statement=GROSS_PROFIT_MARGIN_SQL,
        tables=["transactions", "returns_refunds", "products"],
        inputs=FinanceMetricInput(
            start_date=start_date,
            end_date=end_date,
            product_name=product_name,
            product_category=product_category,
            store_location=store_location,
            payment_method=payment_method,
        ),
        config=config,
    )


@tool(args_schema=FinanceMetricInput)
async def calculate_gross_margin(
    config: RunnableConfig,
    start_date: date | None = None,
    end_date: date | None = None,
    product_name: str | None = None,
    product_category: str | None = None,
    store_location: str | None = None,
    payment_method: str | None = None,
) -> str:
    """Calculate gross margin from recorded sales, refunds, and product cost."""

    return await _run_metric(
        tool_name="calculate_gross_margin",
        metric="gross_margin",
        statement=GROSS_PROFIT_MARGIN_SQL,
        tables=["transactions", "returns_refunds", "products"],
        inputs=FinanceMetricInput(
            start_date=start_date,
            end_date=end_date,
            product_name=product_name,
            product_category=product_category,
            store_location=store_location,
            payment_method=payment_method,
        ),
        config=config,
    )


__all__ = [
    "GROSS_PROFIT_MARGIN_SQL",
    "FinanceMetricInput",
    "NET_SALES_SQL",
    "calculate_gross_margin",
    "calculate_gross_profit",
    "calculate_net_sales",
]
