"""Runtime observability endpoints for agent runs and their events."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from backend.database import connect
from backend.runtime import RunNotFoundError, RunStateError
from backend.workflow import (
    run_business_performance_workflow,
    run_finance_workflow,
)

router = APIRouter(prefix="/api/runs", tags=["observability"])


CREATE_RUN_SQL = """
INSERT INTO agent_runs (run_id, run_type)
VALUES (%(run_id)s, %(run_type)s)
RETURNING
    run_id,
    run_type,
    status,
    created_at,
    started_at,
    completed_at,
    error_message
"""


CREATE_RUN_EVENT_SQL = """
INSERT INTO run_events (run_id, event_type, message)
VALUES (%(run_id)s, 'run_created', 'Run created')
"""


GET_RUN_SQL = """
SELECT
    run_id,
    run_type,
    status,
    created_at,
    started_at,
    completed_at,
    error_message
FROM agent_runs
WHERE run_id = %(run_id)s
"""


GET_RUN_EVENTS_SQL = """
SELECT
    event_id,
    run_id,
    event_type,
    message,
    created_at,
    payload
FROM run_events
WHERE run_id = %(run_id)s
ORDER BY created_at, event_id
"""


class CreateRunRequest(BaseModel):
    """The minimal input required to create an observable agent run."""

    run_type: str = Field(
        min_length=1,
        max_length=100,
        description="Business purpose of the run.",
        examples=["dashboard_analysis"],
    )

    class Config:
        extra = "forbid"


class ExecuteRunRequest(BaseModel):
    """Optional business parameters used by an executable run workflow."""

    month: str | None = Field(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Calendar month in YYYY-MM format.",
        examples=["2025-02"],
    )
    store_id: str | None = Field(
        default=None,
        description="Optional store scope for workflows that support store filtering.",
    )

    class Config:
        extra = "forbid"


class RunResponse(BaseModel):
    """Persisted runtime-observability fields for one agent run."""

    run_id: UUID = Field(description="UUID generated when the run is created.")
    run_type: str = Field(description="Business purpose of the run.")
    status: str = Field(description="Current run status.", examples=["pending"])
    created_at: datetime = Field(description="Timestamp when the run was created.")
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when the run started, if it has started.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when the run completed, if it has completed.",
    )
    error_message: str | None = Field(
        default=None,
        description="Failure detail when the run status is failed.",
    )


class RunEventResponse(BaseModel):
    """One immutable event recorded for an agent run."""

    event_id: int = Field(description="Database-generated event identifier.")
    run_id: UUID = Field(description="UUID of the run that emitted the event.")
    event_type: str = Field(description="Category of the recorded event.")
    message: str = Field(description="Human-readable event message.")
    created_at: datetime = Field(description="Timestamp when the event was created.")
    payload: dict[str, object] = Field(
        description="Optional structured event metadata.",
        examples=[{}],
    )


class ExecuteRunResponse(BaseModel):
    """Completed workflow result for one executable run."""

    run_id: UUID = Field(description="UUID of the executed run.")
    run_type: str = Field(description="Persisted workflow type used for dispatch.")
    status: str = Field(description="Final persisted run status.")
    result: dict[str, object] = Field(description="Unmodified workflow result.")


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _run_response(row: dict[str, object]) -> RunResponse:
    return RunResponse(
        run_id=str(row["run_id"]),
        run_type=row["run_type"],
        status=row["status"],
        created_at=_timestamp(row["created_at"]),
        started_at=_timestamp(row["started_at"]),
        completed_at=_timestamp(row["completed_at"]),
        error_message=row["error_message"],
    )


def _event_response(row: dict[str, object]) -> RunEventResponse:
    return RunEventResponse(
        event_id=row["event_id"],
        run_id=str(row["run_id"]),
        event_type=row["event_type"],
        message=row["message"],
        created_at=_timestamp(row["created_at"]),
        payload=row["payload"],
    )


def _get_run_or_404(run_id: UUID) -> RunResponse:
    """Load one run or raise the API's standard 404 response."""

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(GET_RUN_SQL, {"run_id": run_id})
            run = cursor.fetchone()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return _run_response(dict(run))


@router.post(
    "",
    status_code=201,
    response_model=RunResponse,
    summary="Create an observable run",
    description=(
        "Creates a pending run and its required `run_created` event in one "
        "database transaction."
    ),
    responses={503: {"description": "Database query failed"}},
)
def create_run(request: CreateRunRequest) -> RunResponse:
    """Create a pending run and its required ``run_created`` event atomically."""

    run_id = uuid4()

    try:
        with (
            connect() as connection,
            connection.transaction(),
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                CREATE_RUN_SQL,
                {"run_id": run_id, "run_type": request.run_type},
            )
            run = cursor.fetchone()
            cursor.execute(CREATE_RUN_EVENT_SQL, {"run_id": run_id})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return _run_response(dict(run))


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Get a run",
    description="Returns the current persisted state for one run UUID.",
    responses={
        404: {"description": "Run not found"},
        503: {"description": "Database query failed"},
    },
)
def get_run(run_id: UUID) -> RunResponse:
    """Return one run by its UUID."""

    return _get_run_or_404(run_id)


@router.get(
    "/{run_id}/events",
    response_model=list[RunEventResponse],
    summary="List run events",
    description="Returns all events for one run in creation order.",
    responses={
        404: {"description": "Run not found"},
        503: {"description": "Database query failed"},
    },
)
def get_run_events(run_id: UUID) -> list[RunEventResponse]:
    """Return events belonging to one run in creation order."""

    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(GET_RUN_SQL, {"run_id": run_id})
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Run not found")

            cursor.execute(GET_RUN_EVENTS_SQL, {"run_id": run_id})
            events = [_event_response(dict(row)) for row in cursor.fetchall()]
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return events


@router.post(
    "/{run_id}/execute",
    response_model=ExecuteRunResponse,
    summary="Execute a run workflow",
    description=(
        "Dispatches a pending `finance` or `business_performance` run to its "
        "synchronous Python workflow."
    ),
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is not pending"},
        422: {"description": "Validation error or unsupported run type"},
        503: {"description": "Database query failed"},
    },
)
def execute_run(run_id: UUID, request: ExecuteRunRequest) -> ExecuteRunResponse:
    """Execute one pending run using its persisted workflow type."""

    run = _get_run_or_404(run_id)
    if run.status == "running":
        raise HTTPException(status_code=409, detail="Run is already running")
    if run.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot transition from {run.status} to running",
        )

    try:
        if run.run_type == "finance":
            result = run_finance_workflow(
                run_id=run_id,
                month=request.month,
                store_id=request.store_id,
            )
        elif run.run_type == "business_performance":
            result = run_business_performance_workflow(
                run_id=run_id,
                month=request.month,
                store_id=request.store_id,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported run type: {run.run_type}",
            )
    except HTTPException:
        raise
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    completed_run = _get_run_or_404(run_id)
    return ExecuteRunResponse(
        run_id=run_id,
        run_type=run.run_type,
        status=completed_run.status,
        result=result,
    )
