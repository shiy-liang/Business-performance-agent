"""Financial Pulse dashboard endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from backend.database import connect


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


SUMMARY_SQL = """
WITH parameters AS (
    SELECT
        %(period_start)s::date AS period_start,
        %(period_end)s::date AS period_end,
        %(store_id)s::text AS store_id
),
sales AS (
    SELECT
        COALESCE(SUM(t.net_sales), 0) AS net_sales,
        COALESCE(
            SUM(t.net_sales) FILTER (WHERE p.unit_cost IS NOT NULL),
            0
        ) AS costed_net_sales,
        COALESCE(SUM(t.quantity * p.unit_cost), 0) AS cost_of_goods_sold
    FROM parameters x
    LEFT JOIN transactions t
        ON t.transaction_date >= x.period_start
       AND t.transaction_date < x.period_end
       AND (x.store_id IS NULL OR t.store_id = x.store_id)
    LEFT JOIN products p ON p.product_id = t.product_id
),
refunds AS (
    SELECT
        COALESCE(SUM(r.refund_amount), 0) AS completed_refunds,
        COALESCE(
            SUM(r.refund_amount) FILTER (WHERE p.unit_cost IS NOT NULL),
            0
        ) AS costed_completed_refunds
    FROM parameters x
    LEFT JOIN returns_refunds r
        ON r.return_date >= x.period_start
       AND r.return_date < x.period_end
       AND r.refund_status = 'completed'
    LEFT JOIN transactions t
        ON t.transaction_id = r.transaction_id
       AND (x.store_id IS NULL OR t.store_id = x.store_id)
    LEFT JOIN products p ON p.product_id = t.product_id
    WHERE r.return_id IS NULL
       OR x.store_id IS NULL
       OR t.transaction_id IS NOT NULL
),
operating AS (
    SELECT COALESCE(SUM(e.amount), 0) AS operating_expenses
    FROM parameters x
    LEFT JOIN expenses e
        ON e.expense_date >= x.period_start
       AND e.expense_date < x.period_end
       AND (x.store_id IS NULL OR e.store_id = x.store_id)
),
marketing AS (
    SELECT COALESCE(
        SUM(
            c.budget
            * (
                LEAST(c.end_date, x.period_end - 1)
                - GREATEST(c.start_date, x.period_start)
                + 1
              )::numeric
            / (c.end_date - c.start_date + 1)
        ),
        0
    ) AS allocated_campaign_spend
    FROM parameters x
    LEFT JOIN campaigns c
        ON x.store_id IS NULL
       AND c.start_date < x.period_end
       AND c.end_date >= x.period_start
)
SELECT
    s.net_sales - r.completed_refunds AS refund_adjusted_revenue,
    s.costed_net_sales
        - r.costed_completed_refunds
        - s.cost_of_goods_sold AS estimated_gross_profit,
    s.costed_net_sales
        - r.costed_completed_refunds
        - s.cost_of_goods_sold
        - o.operating_expenses
        - m.allocated_campaign_spend AS estimated_profit
FROM sales s
CROSS JOIN refunds r
CROSS JOIN operating o
CROSS JOIN marketing m
"""


TREND_SQL = """
WITH parameters AS (
    SELECT
        %(first_month)s::date AS first_month,
        %(selected_month)s::date AS selected_month,
        %(store_id)s::text AS store_id
),
months AS (
    SELECT GENERATE_SERIES(
        x.first_month,
        x.selected_month,
        INTERVAL '1 month'
    )::date AS month_start
    FROM parameters x
),
sales AS (
    SELECT
        DATE_TRUNC('month', t.transaction_date)::date AS month_start,
        SUM(t.net_sales) AS net_sales,
        COALESCE(
            SUM(t.net_sales) FILTER (WHERE p.unit_cost IS NOT NULL),
            0
        ) AS costed_net_sales,
        COALESCE(SUM(t.quantity * p.unit_cost), 0) AS cost_of_goods_sold
    FROM parameters x
    JOIN transactions t
      ON t.transaction_date >= x.first_month
     AND t.transaction_date < x.selected_month + INTERVAL '1 month'
     AND (x.store_id IS NULL OR t.store_id = x.store_id)
    LEFT JOIN products p ON p.product_id = t.product_id
    GROUP BY DATE_TRUNC('month', t.transaction_date)::date
),
refunds AS (
    SELECT
        DATE_TRUNC('month', r.return_date)::date AS month_start,
        SUM(r.refund_amount) AS completed_refunds,
        COALESCE(
            SUM(r.refund_amount) FILTER (WHERE p.unit_cost IS NOT NULL),
            0
        ) AS costed_completed_refunds
    FROM parameters x
    JOIN returns_refunds r
      ON r.return_date >= x.first_month
     AND r.return_date < x.selected_month + INTERVAL '1 month'
     AND r.refund_status = 'completed'
    JOIN transactions t ON t.transaction_id = r.transaction_id
    LEFT JOIN products p ON p.product_id = t.product_id
    WHERE x.store_id IS NULL OR t.store_id = x.store_id
    GROUP BY DATE_TRUNC('month', r.return_date)::date
)
SELECT
    TO_CHAR(m.month_start, 'YYYY-MM') AS month,
    COALESCE(s.net_sales, 0)
        - COALESCE(r.completed_refunds, 0) AS refund_adjusted_revenue,
    COALESCE(s.costed_net_sales, 0)
        - COALESCE(r.costed_completed_refunds, 0)
        - COALESCE(s.cost_of_goods_sold, 0) AS estimated_gross_profit
FROM months m
LEFT JOIN sales s USING (month_start)
LEFT JOIN refunds r USING (month_start)
ORDER BY m.month_start
"""


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _previous_month(month_start: date) -> date:
    return (month_start - timedelta(days=1)).replace(day=1)


def _latest_complete_month(max_transaction_date: date) -> date:
    current_month = max_transaction_date.replace(day=1)
    last_day = _next_month(current_month) - timedelta(days=1)
    if max_transaction_date == last_day:
        return current_month
    return _previous_month(current_month)


def _parse_month(value: str) -> date:
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="month must be a valid calendar month in YYYY-MM format",
        ) from exc


def _money(value: Decimal | int | None) -> float:
    return float(round(value or Decimal("0"), 2))


@router.get("/stores")
def list_dashboard_stores() -> dict[str, object]:
    """Return the choices used by the dashboard's store filter."""

    try:
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT store_id, store_location, store_type
                    FROM stores
                    ORDER BY
                        CASE WHEN store_type = 'physical' THEN 0 ELSE 1 END,
                        store_location
                    """
                )
                stores = [dict(row) for row in cursor.fetchall()]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database connection failed") from exc

    return {
        "default_scope": {
            "type": "company",
            "label": "全部门店",
            "includes_online": True,
            "includes_unassigned_transactions": True,
        },
        "stores": stores,
    }


@router.get("/financial-pulse")
def financial_pulse(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Calendar month in YYYY-MM format; defaults to the latest complete month.",
    ),
    store_id: str | None = Query(
        default=None,
        description="Omit for the whole company, including Online and unassigned sales.",
    ),
) -> dict[str, object]:
    """Return the three finance cards and the twelve-month chart."""

    try:
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT MIN(transaction_date) AS first_date,
                           MAX(transaction_date) AS last_date
                    FROM transactions
                    """
                )
                coverage = cursor.fetchone()
                if not coverage or coverage["last_date"] is None:
                    raise HTTPException(status_code=404, detail="No transaction data found")

                if store_id is None:
                    scope = {
                        "type": "company",
                        "store_id": None,
                        "label": "全部门店",
                    }
                else:
                    cursor.execute(
                        """
                        SELECT store_id, store_location, store_type
                        FROM stores
                        WHERE store_id = %s
                        """,
                        (store_id,),
                    )
                    store = cursor.fetchone()
                    if store is None:
                        raise HTTPException(status_code=404, detail="Store not found")
                    scope = {
                        "type": "store",
                        "store_id": store["store_id"],
                        "label": store["store_location"],
                        "store_type": store["store_type"],
                    }

                default_month = _latest_complete_month(coverage["last_date"])
                selected_month = _parse_month(month) if month else default_month
                first_data_month = coverage["first_date"].replace(day=1)
                last_data_month = coverage["last_date"].replace(day=1)
                if not first_data_month <= selected_month <= last_data_month:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "month is outside the available sales range "
                            f"{first_data_month:%Y-%m} to {last_data_month:%Y-%m}"
                        ),
                    )
                period_end = _next_month(selected_month)
                is_complete = selected_month < last_data_month or (
                    selected_month == last_data_month
                    and coverage["last_date"] == period_end - timedelta(days=1)
                )

                cursor.execute(
                    SUMMARY_SQL,
                    {
                        "period_start": selected_month,
                        "period_end": period_end,
                        "store_id": store_id,
                    },
                )
                summary = cursor.fetchone()

                first_trend_month = selected_month
                for _ in range(11):
                    first_trend_month = _previous_month(first_trend_month)

                cursor.execute(
                    TREND_SQL,
                    {
                        "first_month": first_trend_month,
                        "selected_month": selected_month,
                        "store_id": store_id,
                    },
                )
                trend = [
                    {
                        "month": row["month"],
                        "refund_adjusted_revenue": _money(
                            row["refund_adjusted_revenue"]
                        ),
                        "estimated_gross_profit": _money(
                            row["estimated_gross_profit"]
                        ),
                    }
                    for row in cursor.fetchall()
                ]
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    profit_label = "估算经营利润" if store_id is None else "估算门店贡献利润"
    return {
        "scope": scope,
        "period": {
            "month": selected_month.strftime("%Y-%m"),
            "start_date": selected_month.isoformat(),
            "end_date": (period_end - timedelta(days=1)).isoformat(),
            "is_default": month is None,
            "is_complete": is_complete,
            "sales_data_through": coverage["last_date"].isoformat(),
        },
        "metrics": {
            "refund_adjusted_revenue": {
                "label": "退款后营收",
                "value": _money(summary["refund_adjusted_revenue"]),
            },
            "estimated_gross_profit": {
                "label": "估算毛利润",
                "value": _money(summary["estimated_gross_profit"]),
            },
            "estimated_profit": {
                "label": profit_label,
                "value": _money(summary["estimated_profit"]),
            },
        },
        "trend": trend,
    }
