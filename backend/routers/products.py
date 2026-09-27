"""Product Performance dashboard endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from backend.database import connect
from backend.runtime import RunNotFoundError, record_run_event


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


MONTHLY_PRODUCT_SQL = """
WITH parameters AS (
    SELECT
        %(period_start)s::date AS period_start,
        %(period_end)s::date AS period_end,
        %(store_id)s::text AS store_id
),
sales_transactions AS (
    SELECT
        t.transaction_id,
        p.product_id,
        p.product_name,
        p.product_category,
        t.quantity,
        t.net_sales,
        p.unit_cost
    FROM parameters x
    JOIN transactions t
      ON t.transaction_date >= x.period_start
     AND t.transaction_date < x.period_end
     AND (x.store_id IS NULL OR t.store_id = x.store_id)
    JOIN products p ON p.product_id = t.product_id
),
product_totals AS (
    SELECT
        s.product_id,
        s.product_name,
        s.product_category,
        SUM(s.quantity)::bigint AS sold_units,
        COALESCE(SUM(r.return_quantity), 0)::bigint AS returned_units,
        SUM(s.net_sales) AS net_sales,
        COALESCE(SUM(r.refund_amount), 0) AS completed_refunds,
        COALESCE(
            SUM(s.net_sales) FILTER (WHERE s.unit_cost IS NOT NULL),
            0
        ) AS costed_net_sales,
        COALESCE(
            SUM(r.refund_amount) FILTER (WHERE s.unit_cost IS NOT NULL),
            0
        ) AS costed_completed_refunds,
        COALESCE(SUM(s.quantity * s.unit_cost), 0) AS cost_of_goods_sold
    FROM sales_transactions s
    LEFT JOIN returns_refunds r
      ON r.transaction_id = s.transaction_id
     AND LOWER(r.refund_status) = 'completed'
    GROUP BY s.product_id, s.product_name, s.product_category
)
SELECT
    product_id,
    product_name,
    product_category,
    sold_units,
    returned_units,
    sold_units - returned_units AS net_units,
    net_sales - completed_refunds AS refund_adjusted_revenue,
    costed_net_sales
        - costed_completed_refunds
        - cost_of_goods_sold AS estimated_gross_profit,
    CASE
        WHEN sold_units = 0 THEN NULL
        ELSE returned_units::numeric / sold_units
    END AS return_rate
FROM product_totals
"""


LIFETIME_RATINGS_SQL = """
SELECT
    p.product_id,
    p.product_name,
    p.product_category,
    COUNT(r.review_id)::bigint AS review_count,
    AVG(r.rating)::numeric AS average_rating
FROM products p
JOIN customer_reviews r
  ON r.product_name = p.product_name
 AND r.product_category = p.product_category
GROUP BY p.product_id, p.product_name, p.product_category
HAVING COUNT(r.review_id) >= %(minimum_reviews)s
"""

REVENUE_TREND_SQL = """
WITH sale_rows AS (
    SELECT t.transaction_id, t.transaction_date, t.net_sales,
           COALESCE(SUM(r.refund_amount), 0) AS refunds
    FROM transactions t
    JOIN products p ON p.product_id = t.product_id
    LEFT JOIN returns_refunds r
      ON r.transaction_id = t.transaction_id
     AND LOWER(r.refund_status) = 'completed'
    WHERE t.transaction_date >= %(period_start)s
      AND t.transaction_date < %(period_end)s
      AND (%(store_id)s::text IS NULL OR t.store_id = %(store_id)s::text)
    GROUP BY t.transaction_id, t.transaction_date, t.net_sales
)
SELECT DATE_TRUNC(%(grain)s::text, transaction_date::timestamp)::date AS date,
       SUM(net_sales - refunds) AS revenue
FROM sale_rows
GROUP BY 1
ORDER BY 1
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
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="month must be a valid calendar month in YYYY-MM format",
        ) from exc


def _money(value: Decimal | int | None) -> float:
    return float(round(value or Decimal("0"), 2))


def _rate(value: Decimal | int | None) -> float:
    return float(round((value or Decimal("0")) * 100, 2))


def _rating_item(row: dict[str, object]) -> dict[str, object]:
    return {
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "product_category": row["product_category"],
        "average_rating": float(round(row["average_rating"], 2)),
        "review_count": row["review_count"],
    }


def _record_products_failure_if_started(
    run_id: UUID | None,
    products_analysis_started: bool,
    selected_month: date | None,
    store_id: str | None,
    exc: Exception,
) -> None:
    """Record a Products failure without masking the original exception."""

    if not products_analysis_started or run_id is None:
        return
    if selected_month is None:
        return

    error_message = str(exc).strip() or exc.__class__.__name__
    try:
        record_run_event(
            run_id,
            "products_analysis_failed",
            "Products analysis failed",
            {
                "month": selected_month.strftime("%Y-%m"),
                "store_id": store_id,
                "error": error_message,
            },
        )
    except (RunNotFoundError, RuntimeError, psycopg.Error):
        pass


def build_product_performance(
    month: str | None,
    store_id: str | None,
    run_id: UUID | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Build Product Performance from prepared Products context."""

    prepared = prepare_product_performance(
        month=month,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
    )
    return analyze_prepared_product_performance(prepared=prepared, run_id=run_id)


def prepare_product_performance(
    month: str | None,
    store_id: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Validate Products inputs and prepare the context needed for analysis."""

    try:
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT MIN(transaction_date) AS first_date,
                           MAX(transaction_date) AS last_date,
                           (SELECT MAX(return_date) FROM returns_refunds)
                               AS returns_data_through
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
                        "label": "All stores",
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
                period_start = start_date or selected_month.replace(day=1)
                period_end = end_date or _next_month(selected_month)
                if period_end <= period_start:
                    raise HTTPException(status_code=422, detail="end_date must be after start_date")
                if period_start < coverage["first_date"] or period_end - timedelta(days=1) > coverage["last_date"]:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "date range is outside the available sales range "
                            f"{coverage['first_date']} to {coverage['last_date']}"
                        ),
                    )
                is_complete = period_end - timedelta(days=1) <= coverage["last_date"]
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return {
        "scope": scope,
        "coverage": dict(coverage),
        "selected_month": selected_month,
        "period_start": period_start,
        "period_end": period_end,
        "is_default": month is None and start_date is None and end_date is None,
        "is_complete": is_complete,
        "store_id": store_id,
    }


def analyze_prepared_product_performance(
    prepared: dict[str, object],
    run_id: UUID | None,
) -> dict[str, object]:
    """Execute Products SQL and Runtime events using prepared Products context."""

    minimum_reviews = 5
    minimum_units_for_return_rate = 5
    products_analysis_started = False
    scope = prepared["scope"]
    coverage = prepared["coverage"]
    selected_month = prepared["selected_month"]
    period_end = prepared["period_end"]
    store_id = prepared["store_id"]

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            if run_id is not None:
                record_run_event(
                    run_id,
                    "products_analysis_started",
                    "Products analysis started",
                    {
                        "month": selected_month.strftime("%Y-%m"),
                        "store_id": store_id,
                    },
                )
                products_analysis_started = True

            cursor.execute(
                MONTHLY_PRODUCT_SQL,
                {
                    "period_start": prepared["period_start"],
                    "period_end": period_end,
                    "store_id": store_id,
                },
            )
            monthly_rows = [dict(row) for row in cursor.fetchall()]

            grain = (
                "day" if (period_end - prepared["period_start"]).days <= 90
                else "month"
            )
            cursor.execute(
                REVENUE_TREND_SQL,
                {
                    "period_start": prepared["period_start"],
                    "period_end": period_end,
                    "store_id": store_id,
                    "grain": grain,
                },
            )
            revenue_trend = [
                {"date": row["date"].isoformat(), "revenue": _money(row["revenue"])}
                for row in cursor.fetchall()
            ]

            cursor.execute(
                LIFETIME_RATINGS_SQL,
                {"minimum_reviews": minimum_reviews},
            )
            rating_rows = [dict(row) for row in cursor.fetchall()]

        best_rows = sorted(
            (row for row in monthly_rows if row["sold_units"] > 0),
            key=lambda row: (
                row["net_units"],
                row["refund_adjusted_revenue"],
                row["sold_units"],
                row["product_name"],
            ),
            reverse=True,
        )[:5]
        category_totals = {}
        for row in monthly_rows:
            category = row["product_category"] or "Uncategorized"
            category_totals[category] = category_totals.get(category, Decimal("0")) + row["refund_adjusted_revenue"]
        category_share = [
            {"category": category, "revenue": _money(revenue)}
            for category, revenue in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
        ]
        best_sellers = [
            {
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "product_category": row["product_category"],
                "sold_units": row["sold_units"],
                "returned_units": row["returned_units"],
                "net_units": row["net_units"],
                "refund_adjusted_revenue": _money(row["refund_adjusted_revenue"]),
                "estimated_gross_profit": _money(row["estimated_gross_profit"]),
            }
            for row in best_rows
        ]

        return_rows = sorted(
            (
                row
                for row in monthly_rows
                if row["sold_units"] >= minimum_units_for_return_rate
                and row["returned_units"] > 0
            ),
            key=lambda row: (
                row["return_rate"],
                row["returned_units"],
                row["sold_units"],
                row["product_name"],
            ),
            reverse=True,
        )[:5]
        high_return_rate = [
            {
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "product_category": row["product_category"],
                "return_rate_percent": _rate(row["return_rate"]),
                "sold_units": row["sold_units"],
                "returned_units": row["returned_units"],
                "refund_adjusted_revenue": _money(row["refund_adjusted_revenue"]),
            }
            for row in return_rows
        ]

        top_rated_rows = sorted(
            rating_rows,
            key=lambda row: (
                row["average_rating"],
                row["review_count"],
                row["product_name"],
            ),
            reverse=True,
        )[:5]
        lowest_rated_rows = sorted(
            rating_rows,
            key=lambda row: (
                row["average_rating"],
                -row["review_count"],
                row["product_name"],
            ),
        )[:5]

        response = {
            "scope": scope,
            "period": {
                "month": selected_month.strftime("%Y-%m"),
                "start_date": prepared["period_start"].isoformat(),
                "end_date": (period_end - timedelta(days=1)).isoformat(),
                "is_default": prepared["is_default"],
                "is_complete": prepared["is_complete"],
                "sales_data_through": coverage["last_date"].isoformat(),
                "returns_data_through": (
                    coverage["returns_data_through"].isoformat()
                    if coverage["returns_data_through"]
                    else None
                ),
            },
            "basis": {
                "best_sellers": {
                    "ranking": "net_units",
                    "definition": "units sold in the selected month minus completed returned units linked to those same transactions",
                },
                "ratings": {
                    "period": "all_time",
                    "minimum_reviews": minimum_reviews,
                    "store_filter_applied": False,
                    "note": "Reviews have no store_id, so ratings are company-wide product ratings.",
                },
                "high_return_rate": {
                    "definition": "completed returned units linked to the selected month's sales divided by units sold in that cohort",
                    "minimum_sold_units": minimum_units_for_return_rate,
                    "store_filter_applied": True,
                },
                "profit": {
                    "is_estimate": True,
                    "unit_cost_is_synthetic": True,
                    "returned_goods_cost_is_reversed": False,
                },
            },
            "best_sellers": best_sellers,
            "revenue_trend": revenue_trend,
            "category_share": category_share,
            "top_rated": [_rating_item(row) for row in top_rated_rows],
            "high_return_rate": high_return_rate,
            "lowest_rated": [_rating_item(row) for row in lowest_rated_rows],
        }

        if run_id is not None:
            record_run_event(
                run_id,
                "products_analysis_completed",
                "Products analysis completed",
                {
                    "month": selected_month.strftime("%Y-%m"),
                    "store_id": store_id,
                    "product_count": len(monthly_rows),
                },
            )
    except HTTPException:
        raise
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        _record_products_failure_if_started(
            run_id, products_analysis_started, selected_month, store_id, exc
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        _record_products_failure_if_started(
            run_id, products_analysis_started, selected_month, store_id, exc
        )
        raise HTTPException(status_code=503, detail="Database query failed") from exc
    except Exception as exc:
        _record_products_failure_if_started(
            run_id, products_analysis_started, selected_month, store_id, exc
        )
        raise

    return response


@router.get("/product-performance")
def product_performance(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Calendar month in YYYY-MM format; defaults to the latest complete month.",
    ),
    store_id: str | None = Query(
        default=None,
        description="Omit for the whole company, including Online and unassigned sales.",
    ),
    run_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Return four Top-5 product rankings for the dashboard."""

    return build_product_performance(
        month=month,
        store_id=store_id,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )
