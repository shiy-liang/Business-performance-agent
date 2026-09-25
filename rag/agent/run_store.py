"""Best-effort durable audit records for one public Agent run.

The recorder deliberately stores lifecycle metadata and public events only. It
does not persist prompts, chain-of-thought, raw model messages, or streamed answer
tokens. A database outage must never make an otherwise valid Agent answer fail.
"""

from __future__ import annotations

import os
from hashlib import sha256
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from model.config import PROJECT_ROOT
from observability import logger
from rag.agent.state import PublicAgentEvent


load_dotenv(PROJECT_ROOT / ".env")


def _enabled() -> bool:
    return os.getenv("AGENT_RUN_PERSISTENCE", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    return value


def _safe_value(value: Any) -> Any:
    """Bound public event payloads before they enter the audit tables."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 1000 else value[:1000] + "... [truncated]"
    if isinstance(value, dict):
        return {str(key)[:100]: _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:50]]
    return str(value)[:1000]


async def _open_connection() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        _database_url(),
        connect_timeout=5,
        prepare_threshold=None,
    )


class RunRecorder:
    """Persist one run and its public lifecycle events using one connection."""

    def __init__(self, run_id: str) -> None:
        self.run_id = UUID(run_id)
        self._connection: psycopg.AsyncConnection | None = None
        self._available = _enabled()

    async def start(self, question: str) -> None:
        if not self._available:
            return
        try:
            self._connection = await _open_connection()
            await self._connection.execute(
                """
                INSERT INTO agent_runs (run_id, run_type, status, started_at)
                VALUES (%s, 'business_supervisor', 'running', NOW())
                ON CONFLICT (run_id) DO UPDATE SET
                    status = 'running',
                    started_at = COALESCE(agent_runs.started_at, NOW()),
                    completed_at = NULL,
                    error_message = NULL
                """,
                (self.run_id,),
            )
            await self._insert_event(
                "run.started",
                "Business supervisor started",
                {
                    "question_hash": sha256(question.encode("utf-8")).hexdigest()[:16],
                    "question_length": len(question),
                },
            )
            await self._connection.commit()
        except Exception as error:
            await self._disable(error, "agent_run.persistence_start_failed")

    async def record(self, event: PublicAgentEvent) -> None:
        """Record a safe public event; token deltas are intentionally omitted."""

        if not self._available or self._connection is None:
            return
        event_type = str(event.get("event", "event"))
        if event_type == "token":
            return
        data = _safe_value(event.get("data") or {})
        if event_type == "sql_approval":
            # Parameters are intentionally visible to the requesting user but must
            # not be copied into durable audit storage.
            data.pop("parameters", None)
        message = str(data.get("message") or event_type)[:1000]
        try:
            await self._insert_event(event_type, message, data)
            await self._connection.commit()
        except Exception as error:
            await self._disable(error, "agent_run.persistence_event_failed")

    async def complete(self, *, duration_ms: float, evidence_count: int) -> None:
        if not self._available or self._connection is None:
            return
        try:
            await self._insert_event(
                "run.completed",
                "Business supervisor completed",
                {"duration_ms": duration_ms, "evidence_count": evidence_count},
            )
            await self._connection.execute(
                """
                UPDATE agent_runs
                SET status = 'completed', completed_at = NOW(), error_message = NULL
                WHERE run_id = %s
                """,
                (self.run_id,),
            )
            await self._connection.commit()
            await self.close()
        except Exception as error:
            await self._disable(error, "agent_run.persistence_complete_failed")

    async def fail(self, error_code: str) -> None:
        if not self._available or self._connection is None:
            return
        safe_code = error_code[:200]
        try:
            await self._insert_event(
                "run.failed",
                "Business supervisor failed",
                {"error_code": safe_code},
            )
            await self._connection.execute(
                """
                UPDATE agent_runs
                SET status = 'failed', completed_at = NOW(), error_message = %s
                WHERE run_id = %s
                """,
                (safe_code, self.run_id),
            )
            await self._connection.commit()
            await self.close()
        except Exception as error:
            await self._disable(error, "agent_run.persistence_failure_failed")

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                await connection.close()
            except Exception as error:
                logger.warning(
                    "agent_run.persistence_close_failed",
                    message="Agent run audit connection could not be closed cleanly",
                    error_type=type(error).__name__,
                )

    async def _insert_event(
        self,
        event_type: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        if self._connection is None:
            return
        await self._connection.execute(
            """
            INSERT INTO run_events (run_id, event_type, message, payload)
            VALUES (%s, %s, %s, %s)
            """,
            (self.run_id, event_type[:100], message[:1000], Jsonb(payload)),
        )

    async def _disable(self, error: Exception, event: str) -> None:
        logger.warning(
            event,
            message="Agent run audit persistence is unavailable; the Agent will continue",
            error_type=type(error).__name__,
        )
        self._available = False
        await self.close()


__all__ = ["RunRecorder"]
