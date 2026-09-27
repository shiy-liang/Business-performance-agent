"""Structured company-level customer review analytics for workflow use."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from backend.database import connect
from backend.runtime import RunNotFoundError, record_run_event
from config.settings import load_business_rules


_CUSTOMER_EXPERIENCE_RULES = load_business_rules().customer_experience


REVIEW_EXPERIENCE_SQL = """
WITH periods AS (
    SELECT
        'current'::text AS period_name,
        %(current_start)s::date AS period_start,
        %(current_end)s::date AS period_end
    UNION ALL
    SELECT
        'previous'::text AS period_name,
        %(previous_start)s::date AS period_start,
        %(previous_end)s::date AS period_end
)
SELECT
    p.period_name,
    COUNT(r.review_id)::bigint AS review_count,
    ROUND(AVG(r.rating)::numeric, 2) AS average_rating,
    COUNT(r.review_id) FILTER (
        WHERE r.rating <= %(low_rating_max)s::integer
    )::bigint AS low_rating_count,
    CASE
        WHEN COUNT(r.review_id) = 0 THEN 0::numeric
        ELSE ROUND(
            100.0 * COUNT(r.review_id) FILTER (
                WHERE r.rating <= %(low_rating_max)s::integer
            )
            / COUNT(r.review_id),
            2
        )
    END AS low_rating_ratio
FROM periods p
LEFT JOIN customer_reviews r
  ON r.review_date >= p.period_start
 AND r.review_date < p.period_end
GROUP BY p.period_name
ORDER BY CASE p.period_name WHEN 'current' THEN 1 ELSE 2 END
"""


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _previous_month(month_start: date) -> date:
    return (month_start - timedelta(days=1)).replace(day=1)


def _is_complete_month(
    month_start: date,
    first_review_date: date,
    last_review_date: date,
) -> bool:
    month_end = _next_month(month_start) - timedelta(days=1)
    return month_start >= first_review_date and month_end <= last_review_date


def _number(value: Decimal | int | None) -> float | None:
    if value is None:
        return None
    return float(round(value, 2))


def _metrics(row: dict[str, object]) -> dict[str, object]:
    return {
        "review_count": int(row["review_count"]),
        "average_rating": _number(row["average_rating"]),
        "low_rating_count": int(row["low_rating_count"]),
        "low_rating_ratio": _number(row["low_rating_ratio"]),
    }


def _record_review_failure_if_started(
    run_id: UUID | None,
    review_analysis_started: bool,
    selected_month: date | None,
    exc: Exception,
) -> None:
    """Record a Review Analytics failure without masking the original exception."""

    if not review_analysis_started or run_id is None or selected_month is None:
        return

    error_message = str(exc).strip() or exc.__class__.__name__
    try:
        record_run_event(
            run_id,
            "review_analysis_failed",
            "Review analysis failed",
            {
                "month": selected_month.strftime("%Y-%m"),
                "error": error_message,
            },
        )
    except (RunNotFoundError, RuntimeError, psycopg.Error):
        pass


def prepare_review_experience(selected_month: date) -> dict[str, object]:
    """Load review-date coverage for the Finance-resolved calendar month."""

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT MIN(review_date) AS first_review_date,
                       MAX(review_date) AS last_review_date
                FROM customer_reviews
                """
            )
            coverage = cursor.fetchone()
            if not coverage or coverage["last_review_date"] is None:
                raise HTTPException(
                    status_code=404,
                    detail="No customer review data found",
                )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    previous_month = _previous_month(selected_month)
    first_review_date = coverage["first_review_date"]
    last_review_date = coverage["last_review_date"]
    return {
        "coverage": dict(coverage),
        "selected_month": selected_month,
        "period_end": _next_month(selected_month),
        "previous_month": previous_month,
        "previous_period_end": selected_month,
        "is_complete": _is_complete_month(
            selected_month,
            first_review_date,
            last_review_date,
        ),
        "previous_is_complete": _is_complete_month(
            previous_month,
            first_review_date,
            last_review_date,
        ),
    }


def analyze_prepared_review_experience(
    prepared: dict[str, object],
    run_id: UUID | None,
) -> dict[str, object]:
    """Aggregate current and previous company-wide review feedback."""

    review_analysis_started = False
    coverage = prepared["coverage"]
    selected_month = prepared["selected_month"]
    period_end = prepared["period_end"]
    previous_month = prepared["previous_month"]

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            if run_id is not None:
                record_run_event(
                    run_id,
                    "review_analysis_started",
                    "Review analysis started",
                    {"month": selected_month.strftime("%Y-%m")},
                )
                review_analysis_started = True

            cursor.execute(
                REVIEW_EXPERIENCE_SQL,
                {
                    "current_start": selected_month,
                    "current_end": period_end,
                    "previous_start": previous_month,
                    "previous_end": selected_month,
                    "low_rating_max": _CUSTOMER_EXPERIENCE_RULES.low_rating_max,
                },
            )
            rows = {row["period_name"]: dict(row) for row in cursor.fetchall()}

        response = {
            "scope": {
                "type": "company",
                "label": "Company-wide",
                "store_filter_available": False,
            },
            "period": {
                "month": selected_month.strftime("%Y-%m"),
                "start_date": selected_month.isoformat(),
                "end_date": (period_end - timedelta(days=1)).isoformat(),
                "is_complete": prepared["is_complete"],
                "review_data_through": coverage["last_review_date"].isoformat(),
            },
            "baseline_period": {
                "month": previous_month.strftime("%Y-%m"),
                "start_date": previous_month.isoformat(),
                "end_date": (selected_month - timedelta(days=1)).isoformat(),
                "is_complete": prepared["previous_is_complete"],
            },
            "basis": {
                "date_field": "review_date",
                "low_rating_definition": (
                    "rating <= "
                    f"{_CUSTOMER_EXPERIENCE_RULES.low_rating_max}"
                ),
            },
            "current": _metrics(rows["current"]),
            "previous": _metrics(rows["previous"]),
        }

        if run_id is not None:
            record_run_event(
                run_id,
                "review_analysis_completed",
                "Review analysis completed",
                {
                    "month": selected_month.strftime("%Y-%m"),
                    "review_count": response["current"]["review_count"],
                },
            )
    except HTTPException:
        raise
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        _record_review_failure_if_started(
            run_id,
            review_analysis_started,
            selected_month,
            exc,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        _record_review_failure_if_started(
            run_id,
            review_analysis_started,
            selected_month,
            exc,
        )
        raise HTTPException(status_code=503, detail="Database query failed") from exc
    except Exception as exc:
        _record_review_failure_if_started(
            run_id,
            review_analysis_started,
            selected_month,
            exc,
        )
        raise

    return response


__all__ = [
    "analyze_prepared_review_experience",
    "prepare_review_experience",
]
