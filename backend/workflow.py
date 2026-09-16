"""Minimal synchronous workflows for Business Performance Agent runs."""

from __future__ import annotations

from uuid import UUID

import psycopg

from backend.routers.finance import (
    analyze_prepared_financial_pulse,
    prepare_financial_pulse,
)
from backend.runtime import (
    RunNotFoundError,
    RunStateError,
    mark_run_completed,
    mark_run_failed,
    mark_run_running,
)


def _mark_run_failed_preserving_original_exception(
    run_id: UUID, exc: Exception
) -> None:
    """Attempt failure recording without replacing the original exception."""

    error_message = str(exc).strip() or exc.__class__.__name__
    try:
        mark_run_failed(run_id, error_message)
    except (RunNotFoundError, RunStateError, RuntimeError, psycopg.Error):
        pass


def run_finance_workflow(
    run_id: UUID,
    month: str | None = None,
    store_id: str | None = None,
) -> dict[str, object]:
    """Prepare, execute, and persist the lifecycle of one Finance workflow."""

    prepared = prepare_financial_pulse(month=month, store_id=store_id)
    mark_run_running(run_id)

    try:
        result = analyze_prepared_financial_pulse(prepared=prepared, run_id=run_id)
    except Exception as exc:
        _mark_run_failed_preserving_original_exception(run_id, exc)
        raise

    try:
        mark_run_completed(run_id)
    except (RunNotFoundError, RunStateError):
        raise
    except Exception as exc:
        _mark_run_failed_preserving_original_exception(run_id, exc)
        raise

    return result
