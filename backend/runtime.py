"""Runtime lifecycle transitions backed by PostgreSQL."""

from __future__ import annotations

from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.database import connect

SELECT_RUN_STATUS_FOR_UPDATE_SQL = """
SELECT status
FROM agent_runs
WHERE run_id = %(run_id)s
FOR UPDATE
"""


SELECT_RUN_SQL = """
SELECT run_id
FROM agent_runs
WHERE run_id = %(run_id)s
"""


MARK_RUN_RUNNING_SQL = """
UPDATE agent_runs
SET status = 'running', started_at = NOW()
WHERE run_id = %(run_id)s
"""


INSERT_RUN_STARTED_EVENT_SQL = """
INSERT INTO run_events (run_id, event_type, message)
VALUES (%(run_id)s, 'run_started', 'Run started')
"""


MARK_RUN_COMPLETED_SQL = """
UPDATE agent_runs
SET status = 'completed', completed_at = NOW()
WHERE run_id = %(run_id)s
"""


INSERT_RUN_COMPLETED_EVENT_SQL = """
INSERT INTO run_events (run_id, event_type, message)
VALUES (%(run_id)s, 'run_completed', 'Run completed')
"""


MARK_RUN_FAILED_SQL = """
UPDATE agent_runs
SET status = 'failed', completed_at = NOW(), error_message = %(error_message)s
WHERE run_id = %(run_id)s
"""


INSERT_RUN_FAILED_EVENT_SQL = """
INSERT INTO run_events (run_id, event_type, message)
VALUES (%(run_id)s, 'run_failed', 'Run failed')
"""


INSERT_RUN_EVENT_SQL = """
INSERT INTO run_events (run_id, event_type, message, payload)
VALUES (%(run_id)s, %(event_type)s, %(message)s, %(payload)s)
"""


class RunNotFoundError(Exception):
    """Raised when a requested run does not exist."""


class RunStateError(Exception):
    """Raised when a run cannot transition to the requested lifecycle state."""


def mark_run_running(run_id: UUID) -> None:
    """Transition one run from ``pending`` to ``running`` atomically."""

    with (
        connect() as connection,
        connection.transaction(),
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute(SELECT_RUN_STATUS_FOR_UPDATE_SQL, {"run_id": run_id})
        run = cursor.fetchone()

        if run is None:
            raise RunNotFoundError("Run not found")

        status = run["status"]
        if status == "running":
            raise RunStateError("Run is already running")
        if status != "pending":
            raise RunStateError(f"Run cannot transition from {status} to running")

        cursor.execute(MARK_RUN_RUNNING_SQL, {"run_id": run_id})
        cursor.execute(INSERT_RUN_STARTED_EVENT_SQL, {"run_id": run_id})


def mark_run_completed(run_id: UUID) -> None:
    """Transition one run from ``running`` to ``completed`` atomically."""

    with (
        connect() as connection,
        connection.transaction(),
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute(SELECT_RUN_STATUS_FOR_UPDATE_SQL, {"run_id": run_id})
        run = cursor.fetchone()

        if run is None:
            raise RunNotFoundError("Run not found")

        status = run["status"]
        if status == "completed":
            raise RunStateError("Run is already completed")
        if status != "running":
            raise RunStateError(f"Run cannot transition from {status} to completed")

        cursor.execute(MARK_RUN_COMPLETED_SQL, {"run_id": run_id})
        cursor.execute(INSERT_RUN_COMPLETED_EVENT_SQL, {"run_id": run_id})


def mark_run_failed(run_id: UUID, error_message: str) -> None:
    """Transition one pending or running run to ``failed`` atomically."""

    if not isinstance(error_message, str) or not error_message.strip():
        raise ValueError("error_message must be a non-empty string")

    error_message = error_message.strip()

    with (
        connect() as connection,
        connection.transaction(),
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute(SELECT_RUN_STATUS_FOR_UPDATE_SQL, {"run_id": run_id})
        run = cursor.fetchone()

        if run is None:
            raise RunNotFoundError("Run not found")

        status = run["status"]
        if status == "failed":
            raise RunStateError("Run is already failed")
        if status not in {"pending", "running"}:
            raise RunStateError(f"Run cannot transition from {status} to failed")

        cursor.execute(
            MARK_RUN_FAILED_SQL,
            {"run_id": run_id, "error_message": error_message},
        )
        cursor.execute(INSERT_RUN_FAILED_EVENT_SQL, {"run_id": run_id})


def record_run_event(
    run_id: UUID,
    event_type: str,
    message: str,
    payload: dict[str, object] | None = None,
) -> None:
    """Record one event for an existing run."""

    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type must be a non-empty string")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")

    event_type = event_type.strip()
    message = message.strip()
    payload = {} if payload is None else payload

    with (
        connect() as connection,
        connection.transaction(),
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute(SELECT_RUN_SQL, {"run_id": run_id})
        if cursor.fetchone() is None:
            raise RunNotFoundError("Run not found")

        cursor.execute(
            INSERT_RUN_EVENT_SQL,
            {
                "run_id": run_id,
                "event_type": event_type,
                "message": message,
                "payload": Jsonb(payload),
            },
        )
