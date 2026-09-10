"""Marketing Performance dashboard endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from backend.database import connect


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


TOP_CAMPAIGNS_SQL = """
SELECT
    c.campaign_id,
    c.campaign_name,
    c.campaign_type,
    c.start_date,
    c.end_date,
    c.budget,
    c.conversions,
    c.conversion_rate,
    c.roi,
    COUNT(*) OVER () AS active_campaign_count
FROM campaigns c
WHERE c.start_date < %(period_end)s::date
  AND c.end_date >= %(period_start)s::date
ORDER BY c.roi DESC, c.conversions DESC, c.campaign_id
LIMIT 5
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


def _number(value: Decimal | int | None) -> float:
    return float(round(value or Decimal("0"), 2))


@router.get("/marketing-performance")
def marketing_performance(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description=(
            "Calendar month in YYYY-MM format; defaults to the latest complete "
            "transaction month."
        ),
    ),
) -> dict[str, object]:
    """Return the five highest reported-ROI campaigns overlapping a month."""

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

                default_month = _latest_complete_month(coverage["last_date"])
                selected_month = _parse_month(month) if month else default_month
                first_data_month = coverage["first_date"].replace(day=1)
                last_data_month = coverage["last_date"].replace(day=1)
                if not first_data_month <= selected_month <= last_data_month:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "month is outside the available transaction range "
                            f"{first_data_month:%Y-%m} to {last_data_month:%Y-%m}"
                        ),
                    )

                period_end = _next_month(selected_month)
                is_complete = selected_month < last_data_month or (
                    selected_month == last_data_month
                    and coverage["last_date"] == period_end - timedelta(days=1)
                )

                cursor.execute(
                    TOP_CAMPAIGNS_SQL,
                    {
                        "period_start": selected_month,
                        "period_end": period_end,
                    },
                )
                rows = cursor.fetchall()
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    campaigns = [
        {
            "campaign_id": row["campaign_id"],
            "campaign_name": row["campaign_name"],
            "campaign_type": row["campaign_type"],
            "start_date": row["start_date"].isoformat(),
            "end_date": row["end_date"].isoformat(),
            "budget": _number(row["budget"]),
            "conversions": row["conversions"],
            "conversion_rate": _number(row["conversion_rate"]),
            "roi": _number(row["roi"]),
        }
        for row in rows
    ]

    return {
        "scope": {
            "type": "company",
            "label": "全公司",
            "store_filter_available": False,
        },
        "period": {
            "month": selected_month.strftime("%Y-%m"),
            "start_date": selected_month.isoformat(),
            "end_date": (period_end - timedelta(days=1)).isoformat(),
            "is_default": month is None,
            "is_complete": is_complete,
            "transaction_data_through": coverage["last_date"].isoformat(),
        },
        "basis": {
            "selection": "campaign dates overlap the selected calendar month",
            "ranking": "reported roi descending",
            "limit": 5,
            "metrics_period": "campaign_lifecycle",
            "metrics_note": (
                "Budget, conversions, conversion rate, and reported ROI describe "
                "each campaign's full lifecycle; the selected month only determines "
                "which campaigns are included."
            ),
            "attribution": {
                "is_synthetic": True,
                "note": "Campaign attribution data is synthetic and does not prove causality.",
            },
        },
        "active_campaign_count": (
            rows[0]["active_campaign_count"] if rows else 0
        ),
        "campaigns": campaigns,
    }
