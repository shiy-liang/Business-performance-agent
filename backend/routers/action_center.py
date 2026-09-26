"""Urgent Action Center dashboard endpoint."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from backend.database import connect
from backend.runtime import RunNotFoundError, record_run_event


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


INVENTORY_ALERTS_SQL = """
WITH latest_snapshot AS (
    SELECT MAX(snapshot_date) AS snapshot_date
    FROM inventory
)
SELECT
    i.inventory_id,
    i.product_id,
    p.product_name,
    p.product_category,
    i.store_id,
    s.store_location,
    i.stock_quantity,
    i.reorder_level,
    CASE
        WHEN i.reorder_level = 0 THEN 0::numeric
        ELSE i.stock_quantity::numeric / i.reorder_level
    END AS stock_ratio,
    CASE
        WHEN i.reorder_level = 0 OR i.stock_quantity * 4 <= i.reorder_level
            THEN 'critical'
        WHEN i.stock_quantity * 2 <= i.reorder_level
            THEN 'high'
        ELSE 'warning'
    END AS severity,
    i.snapshot_date,
    i.is_synthetic
FROM inventory i
JOIN latest_snapshot latest ON latest.snapshot_date = i.snapshot_date
JOIN products p ON p.product_id = i.product_id
JOIN stores s ON s.store_id = i.store_id
WHERE i.needs_reorder IS TRUE
  AND (%(store_id)s::text IS NULL OR i.store_id = %(store_id)s::text)
ORDER BY
    CASE
        WHEN i.reorder_level = 0 OR i.stock_quantity * 4 <= i.reorder_level THEN 0
        WHEN i.stock_quantity * 2 <= i.reorder_level THEN 1
        ELSE 2
    END,
    CASE
        WHEN i.reorder_level = 0 THEN 0::numeric
        ELSE i.stock_quantity::numeric / i.reorder_level
    END,
    (i.reorder_level - i.stock_quantity) DESC,
    p.product_name,
    s.store_location
"""


OLDEST_TICKETS_SQL = """
WITH ticket_data_date AS (
    SELECT MAX(submission_date) AS data_through
    FROM support_tickets
),
ranked AS (
    SELECT
        t.ticket_id,
        t.issue_category,
        t.submission_date,
        t.resolution_status,
        t.notes,
        d.data_through,
        d.data_through - t.submission_date AS open_days,
        COUNT(*) OVER () AS unresolved_high_priority_count
    FROM support_tickets t
    CROSS JOIN ticket_data_date d
    WHERE LOWER(t.priority) = 'high'
      AND LOWER(t.resolution_status) IN ('pending', 'escalated')
)
SELECT *
FROM ranked
ORDER BY
    submission_date,
    ticket_id
LIMIT 3
"""


def _ratio(value: Decimal | int | None) -> float:
    return float(round(value or Decimal("0"), 4))


def _record_action_center_failure_if_started(
    run_id: UUID | None,
    action_center_analysis_started: bool,
    store_id: str | None,
    exc: Exception,
) -> None:
    """Record an Action Center failure without masking the original exception."""

    if not action_center_analysis_started or run_id is None:
        return

    error_message = str(exc).strip() or exc.__class__.__name__
    try:
        record_run_event(
            run_id,
            "action_center_analysis_failed",
            "Action Center analysis failed",
            {
                "store_id": store_id,
                "error": error_message,
            },
        )
    except (RunNotFoundError, RuntimeError, psycopg.Error):
        pass


def build_action_center(
    store_id: str | None,
    run_id: UUID | None,
) -> dict[str, object]:
    """Build Action Center from prepared Action Center context."""

    prepared = prepare_action_center(store_id=store_id)
    return analyze_prepared_action_center(prepared=prepared, run_id=run_id)


def prepare_action_center(store_id: str | None) -> dict[str, object]:
    """Validate the optional inventory store scope before analysis."""

    if store_id is None:
        return {
            "inventory_scope": {
                "type": "company",
                "store_id": None,
                "label": "All stores",
            },
            "store_id": None,
        }

    try:
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
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
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return {
        "inventory_scope": {
            "type": "store",
            "store_id": store["store_id"],
            "label": store["store_location"],
            "store_type": store["store_type"],
        },
        "store_id": store_id,
    }


def analyze_prepared_action_center(
    prepared: dict[str, object],
    run_id: UUID | None,
) -> dict[str, object]:
    """Execute Action Center analysis and Runtime events from prepared context."""

    action_center_analysis_started = False
    inventory_scope = prepared["inventory_scope"]
    store_id = prepared["store_id"]

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            if run_id is not None:
                record_run_event(
                    run_id,
                    "action_center_analysis_started",
                    "Action Center analysis started",
                    {"store_id": store_id},
                )
                action_center_analysis_started = True

            cursor.execute(
                """
                WITH latest_snapshot AS (
                    SELECT MAX(snapshot_date) AS snapshot_date
                    FROM inventory
                )
                SELECT
                    latest.snapshot_date,
                    COALESCE(BOOL_OR(i.is_synthetic), FALSE) AS is_synthetic,
                    COUNT(i.inventory_id)::bigint AS total_inventory_count
                FROM latest_snapshot latest
                LEFT JOIN inventory i
                  ON i.snapshot_date = latest.snapshot_date
                 AND (
                     %(store_id)s::text IS NULL
                     OR i.store_id = %(store_id)s::text
                 )
                GROUP BY latest.snapshot_date
                """,
                {"store_id": store_id},
            )
            inventory_metadata = cursor.fetchone()

            cursor.execute(INVENTORY_ALERTS_SQL, {"store_id": store_id})
            inventory_rows = cursor.fetchall()
            critical_count = sum(
                row["severity"] == "critical" for row in inventory_rows
            )
            top_inventory = [
                {
                    "inventory_id": row["inventory_id"],
                    "product_id": row["product_id"],
                    "product_name": row["product_name"],
                    "product_category": row["product_category"],
                    "store_id": row["store_id"],
                    "store_location": row["store_location"],
                    "stock_quantity": row["stock_quantity"],
                    "reorder_level": row["reorder_level"],
                    "stock_ratio": _ratio(row["stock_ratio"]),
                    "severity": row["severity"],
                }
                for row in inventory_rows[:5]
            ]
            inventory_snapshot = (
                inventory_metadata["snapshot_date"].isoformat()
                if inventory_metadata and inventory_metadata["snapshot_date"]
                else None
            )
            inventory_is_synthetic = bool(
                inventory_metadata and inventory_metadata["is_synthetic"]
            )
            total_inventory_count = int(
                inventory_metadata["total_inventory_count"]
                if inventory_metadata
                else 0
            )
            affected_inventory_count = len(inventory_rows)
            affected_ratio = (
                round(
                    affected_inventory_count / total_inventory_count * 100,
                    2,
                )
                if total_inventory_count > 0
                else 0.0
            )

            cursor.execute(OLDEST_TICKETS_SQL)
            ticket_rows = cursor.fetchall()
            oldest_tickets = [
                {
                    "ticket_id": row["ticket_id"],
                    "issue_category": row["issue_category"],
                    "submission_date": row["submission_date"].isoformat(),
                    "resolution_status": row["resolution_status"],
                    "open_days": row["open_days"],
                    "notes": row["notes"],
                }
                for row in ticket_rows
            ]
            unresolved_ticket_count = (
                ticket_rows[0]["unresolved_high_priority_count"]
                if ticket_rows
                else 0
            )
            ticket_data_through = (
                ticket_rows[0]["data_through"].isoformat()
                if ticket_rows and ticket_rows[0]["data_through"]
                else None
            )

        response = {
            "inventory": {
                "scope": inventory_scope,
                "snapshot_date": inventory_snapshot,
                "is_synthetic": inventory_is_synthetic,
                "total_inventory_count": total_inventory_count,
                "critical_count": critical_count,
                "additional_reorder_count": len(inventory_rows) - critical_count,
                "affected_ratio": affected_ratio,
                "top_items": top_inventory,
            },
            "support_tickets": {
                "scope": {
                    "type": "company",
                    "label": "Company-wide",
                    "store_filter_available": False,
                },
                "data_through": ticket_data_through,
                "unresolved_high_priority_count": unresolved_ticket_count,
                "age_basis": "submission_date",
                "oldest": oldest_tickets,
            },
        }

        if run_id is not None:
            record_run_event(
                run_id,
                "action_center_analysis_completed",
                "Action Center analysis completed",
                {"store_id": store_id},
            )
    except HTTPException:
        raise
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        _record_action_center_failure_if_started(
            run_id, action_center_analysis_started, store_id, exc
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        _record_action_center_failure_if_started(
            run_id, action_center_analysis_started, store_id, exc
        )
        raise HTTPException(status_code=503, detail="Database query failed") from exc
    except Exception as exc:
        _record_action_center_failure_if_started(
            run_id, action_center_analysis_started, store_id, exc
        )
        raise

    return response


@router.get("/action-center")
def action_center(
    store_id: str | None = Query(
        default=None,
        description="Omit for company-wide inventory; tickets are always company-wide.",
    ),
    run_id: UUID | None = None,
) -> dict[str, object]:
    """Return severe stock alerts and the oldest unresolved priority tickets."""

    return build_action_center(store_id=store_id, run_id=run_id)
