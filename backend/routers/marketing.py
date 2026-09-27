"""Marketing Performance dashboard endpoint."""

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


TOP_CAMPAIGNS_SQL = """
WITH selected_campaigns AS (
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
)
SELECT
    selected_campaigns.*,
    (
        SELECT COUNT(*)::bigint
        FROM transactions t
        WHERE t.transaction_date >= selected_campaigns.start_date
          AND t.transaction_date <= selected_campaigns.end_date
    ) AS transactions_during_campaign
FROM selected_campaigns
ORDER BY roi DESC, conversions DESC, campaign_id
"""


CAMPAIGN_RISK_SUMMARY_SQL = """
SELECT
    COUNT(*)::bigint AS active_campaign_count,
    COUNT(*) FILTER (WHERE c.roi < 0)::bigint AS negative_roi_campaign_count,
    CASE
        WHEN COUNT(*) = 0 THEN 0::numeric
        ELSE ROUND(
            100.0 * COUNT(*) FILTER (WHERE c.roi < 0) / COUNT(*),
            2
        )
    END AS negative_roi_ratio,
    MIN(c.roi) FILTER (WHERE c.roi < 0) AS lowest_reported_roi
FROM campaigns c
WHERE c.start_date < %(period_end)s::date
  AND c.end_date >= %(period_start)s::date
"""


LOWEST_NEGATIVE_ROI_CAMPAIGNS_SQL = """
SELECT
    c.campaign_id,
    c.campaign_name,
    c.start_date,
    c.end_date,
    c.budget,
    c.conversion_rate,
    c.roi AS reported_roi
FROM campaigns c
WHERE c.start_date < %(period_end)s::date
  AND c.end_date >= %(period_start)s::date
  AND c.roi < 0
ORDER BY c.roi, c.campaign_id
LIMIT 3
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


def _record_marketing_failure_if_started(
    run_id: UUID | None,
    marketing_analysis_started: bool,
    selected_month: date | None,
    exc: Exception,
) -> None:
    """Record a Marketing failure without masking the original exception."""

    if not marketing_analysis_started or run_id is None:
        return
    if selected_month is None:
        return

    error_message = str(exc).strip() or exc.__class__.__name__
    try:
        record_run_event(
            run_id,
            "marketing_analysis_failed",
            "Marketing analysis failed",
            {
                "month": selected_month.strftime("%Y-%m"),
                "error": error_message,
            },
        )
    except (RunNotFoundError, RuntimeError, psycopg.Error):
        pass


def build_marketing_performance(
    month: str | None,
    run_id: UUID | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Build Marketing Performance from prepared Marketing context."""

    prepared = prepare_marketing_performance(month=month, start_date=start_date, end_date=end_date)
    return analyze_prepared_marketing_performance(prepared=prepared, run_id=run_id)


def prepare_marketing_performance(
    month: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Validate Marketing inputs and prepare the context needed for analysis."""

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
                selected_month = (
                    _parse_month(month)
                    if month
                    else start_date.replace(day=1) if start_date else default_month
                )
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

                period_start = start_date or selected_month
                period_end = end_date or _next_month(selected_month)
                if period_end <= period_start:
                    raise HTTPException(status_code=422, detail="end_date must be after start_date")
                is_complete = period_end - timedelta(days=1) <= coverage["last_date"]
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return {
        "coverage": dict(coverage),
        "selected_month": selected_month,
        "period_start": period_start,
        "period_end": period_end,
        "is_default": month is None and start_date is None and end_date is None,
        "is_complete": is_complete,
    }


def analyze_prepared_marketing_performance(
    prepared: dict[str, object],
    run_id: UUID | None,
) -> dict[str, object]:
    """Execute Marketing SQL and Runtime events using prepared Marketing context."""

    marketing_analysis_started = False
    coverage = prepared["coverage"]
    selected_month = prepared["selected_month"]
    period_start = prepared["period_start"]
    period_end = prepared["period_end"]

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            if run_id is not None:
                record_run_event(
                    run_id,
                    "marketing_analysis_started",
                    "Marketing analysis started",
                    {"month": selected_month.strftime("%Y-%m")},
                )
                marketing_analysis_started = True

            parameters = {
                "period_start": period_start,
                "period_end": period_end,
            }
            cursor.execute(TOP_CAMPAIGNS_SQL, parameters)
            rows = cursor.fetchall()

            cursor.execute(CAMPAIGN_RISK_SUMMARY_SQL, parameters)
            risk_summary_row = cursor.fetchone()

            cursor.execute(LOWEST_NEGATIVE_ROI_CAMPAIGNS_SQL, parameters)
            representative_rows = cursor.fetchall()

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
                "transactions_during_campaign": row["transactions_during_campaign"],
            }
            for row in rows
        ]
        representative_campaigns = [
            {
                "campaign_id": row["campaign_id"],
                "campaign_name": row["campaign_name"],
                "start_date": row["start_date"].isoformat(),
                "end_date": row["end_date"].isoformat(),
                "budget": _number(row["budget"]),
                "conversion_rate": _number(row["conversion_rate"]),
                "reported_roi": _number(row["reported_roi"]),
            }
            for row in representative_rows
        ]
        lowest_reported_roi = (
            _number(risk_summary_row["lowest_reported_roi"])
            if risk_summary_row["lowest_reported_roi"] is not None
            else None
        )

        response = {
            "scope": {
                "type": "company",
                "label": "Company-wide",
                "store_filter_available": False,
            },
            "period": {
                "month": selected_month.strftime("%Y-%m"),
                "start_date": period_start.isoformat(),
                "end_date": (period_end - timedelta(days=1)).isoformat(),
                "is_default": prepared["is_default"],
                "is_complete": prepared["is_complete"],
                "transaction_data_through": coverage["last_date"].isoformat(),
            },
            "basis": {
                "selection": "campaign dates overlap the selected date range",
                "ranking": "reported roi descending",
                "limit": 5,
                "metrics_period": "campaign_lifecycle",
                "metrics_note": (
                    "Budget, conversions, conversion rate, and reported ROI describe "
                    "each campaign's full lifecycle; the selected month only determines "
                    "which campaigns are included."
                ),
                "transaction_count_note": (
                    "Transactions during a campaign count all company-wide transactions "
                    "dated inclusively between its start and end dates; they are not "
                    "necessarily attributable to the campaign."
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
            "risk_summary": {
                "active_campaign_count": risk_summary_row[
                    "active_campaign_count"
                ],
                "negative_roi_campaign_count": risk_summary_row[
                    "negative_roi_campaign_count"
                ],
                "negative_roi_ratio": _number(
                    risk_summary_row["negative_roi_ratio"]
                ),
                "lowest_reported_roi": lowest_reported_roi,
                "representative_campaigns": representative_campaigns,
            },
        }

        if run_id is not None:
            record_run_event(
                run_id,
                "marketing_analysis_completed",
                "Marketing analysis completed",
                {
                    "month": selected_month.strftime("%Y-%m"),
                    "campaign_count": len(campaigns),
                },
            )
    except HTTPException:
        raise
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        _record_marketing_failure_if_started(
            run_id, marketing_analysis_started, selected_month, exc
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        _record_marketing_failure_if_started(
            run_id, marketing_analysis_started, selected_month, exc
        )
        raise HTTPException(status_code=503, detail="Database query failed") from exc
    except Exception as exc:
        _record_marketing_failure_if_started(
            run_id, marketing_analysis_started, selected_month, exc
        )
        raise

    return response


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
    run_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Return the five highest reported-ROI campaigns overlapping the selected range."""

    return build_marketing_performance(
        month=month,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )
