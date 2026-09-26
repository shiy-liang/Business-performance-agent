"""Semantic retrieval for concrete descriptions inside support tickets."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from time import perf_counter
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field, model_validator

from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards
from rag.agent.tools.operations.skill_loader import selected_operations_skills


MAX_CONCRETE_PROBLEM_CALLS = 1
REQUIRED_SKILL = "support_ticket_problem_retrieval"


def _minimum_similarity() -> float:
    try:
        value = float(os.getenv("AGENT_TICKET_MIN_SIMILARITY", "0.25"))
    except ValueError:
        return 0.25
    return value if -1.0 <= value <= 1.0 else 0.25


class ConcreteProblemInput(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=500,
        description=(
            "A concise semantic description of the concrete support-ticket problem "
            "to find, preserving the user's topic and wording."
        ),
    )
    start_date: date | None = Field(
        default=None,
        description="Optional inclusive ticket submission-date lower bound.",
    )
    end_date: date | None = Field(
        default=None,
        description="Optional exclusive ticket submission-date upper bound.",
    )
    issue_category: str | None = Field(default=None, max_length=200)
    priority: str | None = Field(default=None, max_length=100)
    resolution_status: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_dates(self) -> "ConcreteProblemInput":
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must be earlier than end_date")
        return self


def _runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("ticket_problem_runtime_state")
    if not isinstance(state, dict):
        state = {"calls": 0, "in_flight": False}
        configurable["ticket_problem_runtime_state"] = state
    state.setdefault("calls", 0)
    state.setdefault("in_flight", False)
    return state


def _claim_call(config: RunnableConfig) -> tuple[str, int]:
    state = _runtime_state(config)
    calls = int(state.get("calls", 0))
    if state.get("in_flight") is True:
        return "concurrent_query_blocked", calls
    if calls >= MAX_CONCRETE_PROBLEM_CALLS:
        return "attempt_limit", calls
    state["calls"] = calls + 1
    state["in_flight"] = True
    return "permitted", calls + 1


def _finish_call(config: RunnableConfig) -> None:
    _runtime_state(config)["in_flight"] = False


def _search_ticket_problems(
    query_vector: list[float],
    filters: ConcreteProblemInput,
) -> list[dict[str, Any]]:
    vector = Vector(query_vector)
    threshold = _minimum_similarity()
    parameters = {
        "vector": vector,
        "dimensions": len(query_vector),
        "start_date": filters.start_date,
        "end_date": filters.end_date,
        "issue_category": filters.issue_category,
        "priority": filters.priority,
        "resolution_status": filters.resolution_status,
        "minimum_similarity": threshold,
        "top_k": filters.top_k,
    }
    with connect_readonly() as connection:
        with connection.cursor() as guard_cursor:
            set_readonly_guards(guard_cursor)
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ticket_id,
                    customer_id,
                    issue_category,
                    priority,
                    submission_date,
                    resolution_date,
                    resolution_status,
                    resolution_time_hours,
                    customer_satisfaction_score,
                    notes,
                    1 - (embedding <=> %(vector)s) AS similarity
                FROM public.support_tickets
                WHERE embedding IS NOT NULL
                  AND notes IS NOT NULL
                  AND BTRIM(notes) <> ''
                  AND vector_dims(embedding) = %(dimensions)s
                  AND (%(start_date)s::date IS NULL OR submission_date >= %(start_date)s::date)
                  AND (%(end_date)s::date IS NULL OR submission_date < %(end_date)s::date)
                  AND (
                        %(issue_category)s::text IS NULL
                        OR LOWER(issue_category) = LOWER(%(issue_category)s::text)
                  )
                  AND (
                        %(priority)s::text IS NULL
                        OR LOWER(priority) = LOWER(%(priority)s::text)
                  )
                  AND (
                        %(resolution_status)s::text IS NULL
                        OR LOWER(resolution_status) = LOWER(%(resolution_status)s::text)
                  )
                  AND 1 - (embedding <=> %(vector)s) >= %(minimum_similarity)s
                ORDER BY embedding <=> %(vector)s, submission_date DESC, ticket_id
                LIMIT %(top_k)s
                """,
                parameters,
            )
            rows = cursor.fetchall()

    return [
        {
            "ticket_id": row[0],
            "customer_id": row[1],
            "issue_category": row[2],
            "priority": row[3],
            "submission_date": row[4].isoformat(),
            "resolution_date": row[5].isoformat() if row[5] is not None else None,
            "resolution_status": row[6],
            "resolution_time_hours": (
                float(row[7]) if row[7] is not None else None
            ),
            "customer_satisfaction_score": row[8],
            "notes": row[9],
            "similarity": round(float(row[10]), 6),
            "citation": f"[ticket:{row[0]}]",
        }
        for row in rows
    ]


def _sources(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "support_ticket",
            "filename": f"Support ticket · {match['ticket_id']}",
            "ticket_id": match["ticket_id"],
            "citation": match["citation"],
            "similarity": match["similarity"],
        }
        for match in matches
    ]


def _blocked_payload(error_type: str) -> str:
    if error_type == "concurrent_query_blocked":
        error = "Another concrete-problem retrieval is already running."
    else:
        error = "check_concrete_problem may be called only once per Operations run."
    return json.dumps(
        {
            "success": False,
            "agent": "operations",
            "tool": "check_concrete_problem",
            "evidence_kind": "support_ticket_problem",
            "error_type": error_type,
            "error": error,
            "retryable": False,
            "matches": [],
            "sources": [],
        },
        ensure_ascii=False,
    )


@tool(args_schema=ConcreteProblemInput)
async def check_concrete_problem(
    query: str,
    config: RunnableConfig,
    start_date: date | None = None,
    end_date: date | None = None,
    issue_category: str | None = None,
    priority: str | None = None,
    resolution_status: str | None = None,
    top_k: int = 5,
) -> str:
    """Retrieve support tickets whose note text matches a concrete problem description."""

    tool_name = "check_concrete_problem"
    if REQUIRED_SKILL not in selected_operations_skills(config):
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type="skill_not_loaded",
        )
        return json.dumps(
            {
                "success": False,
                "agent": "operations",
                "tool": tool_name,
                "evidence_kind": "support_ticket_problem",
                "error_type": "skill_not_loaded",
                "error": (
                    "Load the support_ticket_problem_retrieval skill before "
                    "calling check_concrete_problem."
                ),
                "retryable": True,
                "matches": [],
                "sources": [],
            },
            ensure_ascii=False,
        )
    claim_status, call_number = _claim_call(config)
    if claim_status != "permitted":
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type=claim_status,
            call_number=call_number,
        )
        return _blocked_payload(claim_status)

    inputs = ConcreteProblemInput(
        query=query,
        start_date=start_date,
        end_date=end_date,
        issue_category=issue_category,
        priority=priority,
        resolution_status=resolution_status,
        top_k=top_k,
    )
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        call_number=call_number,
        top_k=top_k,
        query_length=len(query),
        filtered=any(
            value is not None
            for value in (
                start_date,
                end_date,
                issue_category,
                priority,
                resolution_status,
            )
        ),
    )
    matches: list[dict[str, Any]] = []
    try:
        query_vector = await embedding_model.aembed_query(query)
        matches = await asyncio.to_thread(_search_ticket_problems, query_vector, inputs)
        payload = {
            "success": True,
            "agent": "operations",
            "tool": tool_name,
            "evidence_kind": "support_ticket_problem",
            "call_number": call_number,
            "query": query,
            "filters": inputs.model_dump(mode="json", exclude={"query", "top_k"}),
            "minimum_similarity": _minimum_similarity(),
            "matches": matches,
            "sources": _sources(matches),
        }
    except Exception as error:
        logger.exception("tool.failed", error, component="tool", tool_name=tool_name)
        payload = {
            "success": False,
            "agent": "operations",
            "tool": tool_name,
            "evidence_kind": "support_ticket_problem",
            "error_type": "retrieval_error",
            "error": "Concrete support-ticket descriptions are temporarily unavailable.",
            "query": query,
            "filters": inputs.model_dump(mode="json", exclude={"query", "top_k"}),
            "matches": [],
            "sources": [],
        }
    finally:
        _finish_call(config)

    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=payload["success"],
        call_number=call_number,
        match_count=len(matches),
        error_type=payload.get("error_type"),
        minimum_similarity=_minimum_similarity(),
    )
    return json.dumps(payload, ensure_ascii=False, default=str)


__all__ = [
    "ConcreteProblemInput",
    "MAX_CONCRETE_PROBLEM_CALLS",
    "REQUIRED_SKILL",
    "check_concrete_problem",
]
