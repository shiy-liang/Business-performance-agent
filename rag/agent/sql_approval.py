"""Coordinate one-time user approval for model-generated SQL queries."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from config.settings import load_agent_settings


SqlApprovalDecision = Literal["execute", "cancel"]


def _approval_timeout_seconds() -> int:
    return load_agent_settings().sql.approval_timeout_seconds


@dataclass(slots=True)
class PendingSqlApproval:
    """One SQL decision that is waiting for the browser user."""

    approval_id: str
    run_id: str
    agent_name: str
    future: asyncio.Future[SqlApprovalDecision]


class SqlApprovalNotFoundError(KeyError):
    """Raised when an approval no longer exists or belongs to another run."""


class SqlApprovalAlreadyDecidedError(RuntimeError):
    """Raised when a browser submits a second decision for one approval."""


class SqlApprovalManager:
    """Keep pending approvals in memory while their SSE request remains active."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingSqlApproval] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        run_id: str,
        agent_name: str,
    ) -> PendingSqlApproval:
        """Register an approval before its public event is emitted."""

        loop = asyncio.get_running_loop()
        pending = PendingSqlApproval(
            approval_id=str(uuid4()),
            run_id=run_id,
            agent_name=agent_name,
            future=loop.create_future(),
        )
        async with self._lock:
            self._pending[pending.approval_id] = pending
        return pending

    async def wait(self, pending: PendingSqlApproval) -> SqlApprovalDecision:
        """Wait for a registered approval and always remove it afterward."""

        try:
            return await asyncio.wait_for(
                asyncio.shield(pending.future),
                timeout=_approval_timeout_seconds(),
            )
        finally:
            async with self._lock:
                self._pending.pop(pending.approval_id, None)
            if not pending.future.done():
                pending.future.cancel()

    async def decide(
        self,
        approval_id: str,
        decision: SqlApprovalDecision,
        *,
        run_id: str | None = None,
    ) -> PendingSqlApproval:
        """Resolve one pending approval exactly once."""

        async with self._lock:
            pending = self._pending.get(approval_id)
            if pending is None or (run_id is not None and pending.run_id != run_id):
                raise SqlApprovalNotFoundError(approval_id)
            if pending.future.done():
                raise SqlApprovalAlreadyDecidedError(approval_id)
            pending.future.set_result(decision)
            return pending

    async def clear(self) -> None:
        """Cancel every pending approval. Intended for shutdown and tests."""

        async with self._lock:
            pending_items = list(self._pending.values())
            self._pending.clear()
        for pending in pending_items:
            if not pending.future.done():
                pending.future.cancel()


sql_approval_manager = SqlApprovalManager()


__all__ = [
    "PendingSqlApproval",
    "SqlApprovalAlreadyDecidedError",
    "SqlApprovalDecision",
    "SqlApprovalManager",
    "SqlApprovalNotFoundError",
    "sql_approval_manager",
]
