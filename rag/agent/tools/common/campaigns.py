"""Shared semantic resolution of fuzzy campaign terms to stored campaign names."""

from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field

from config.settings import load_agent_settings
from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


_CAMPAIGN_SETTINGS = load_agent_settings().campaign_resolution
CAMPAIGN_NAME_TOP_K = _CAMPAIGN_SETTINGS.top_k
CAMPAIGN_NAME_SIMILARITY_THRESHOLDS = _CAMPAIGN_SETTINGS.similarity_thresholds
MIN_SIMILARITY = CAMPAIGN_NAME_SIMILARITY_THRESHOLDS[0]
MAX_CAMPAIGN_NAME_ATTEMPTS = len(CAMPAIGN_NAME_SIMILARITY_THRESHOLDS)
MAX_SIMILARITY_GAP = _CAMPAIGN_SETTINGS.max_similarity_gap

CAMPAIGN_NAME_SEARCH_SQL = """
SELECT
    campaign_id,
    campaign_name,
    campaign_type,
    start_date,
    end_date,
    1 - (embedding <=> %(query_embedding)s) AS similarity
FROM public.campaigns
WHERE embedding IS NOT NULL
  AND vector_dims(embedding) = %(dimensions)s
ORDER BY similarity DESC, campaign_name ASC
LIMIT %(top_k)s
"""


class FindRealCampaignNameInput(BaseModel):
    """One fuzzy campaign phrase supplied by the caller."""

    query: str = Field(
        min_length=1,
        max_length=_CAMPAIGN_SETTINGS.max_query_length,
        description=(
            "A fuzzy, abbreviated, non-standard, or cross-language campaign name "
            "from the user."
        ),
    )


def _search_campaign_candidates(query_vector: list[float]) -> list[dict[str, Any]]:
    """Execute the fixed Top-5 campaign pgvector query read-only."""

    vector = Vector(query_vector)
    with connect_readonly() as connection:
        with connection.cursor() as guard_cursor:
            set_readonly_guards(guard_cursor)
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                CAMPAIGN_NAME_SEARCH_SQL,
                {
                    "query_embedding": vector,
                    "dimensions": len(query_vector),
                    "top_k": CAMPAIGN_NAME_TOP_K,
                },
            )
            rows = cursor.fetchall()

    return [
        {
            "campaign_id": row[0],
            "campaign_name": row[1],
            "campaign_type": row[2],
            "start_date": row[3].isoformat(),
            "end_date": row[4].isoformat(),
            "similarity": float(row[5]),
        }
        for row in rows
    ]


def _filter_campaign_candidates(
    candidates: list[dict[str, Any]],
    minimum_similarity: float = MIN_SIMILARITY,
) -> list[dict[str, Any]]:
    """Apply the product resolver's threshold and adjacent-score gap rules."""

    accepted: list[dict[str, Any]] = []
    previous_similarity: float | None = None
    for candidate in candidates:
        similarity = float(candidate["similarity"])
        if similarity < minimum_similarity:
            break
        if (
            previous_similarity is not None
            and previous_similarity - similarity > MAX_SIMILARITY_GAP
        ):
            break
        accepted.append(candidate)
        previous_similarity = similarity
    return accepted


def _campaign_resolution_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("campaign_resolution_runtime_state")
    if not isinstance(state, dict):
        state = {
            "attempts": 0,
            "in_flight": False,
            "resolved": False,
            "accepted_campaign_names": [],
        }
        configurable["campaign_resolution_runtime_state"] = state
    state.setdefault("attempts", 0)
    state.setdefault("in_flight", False)
    state.setdefault("resolved", False)
    state.setdefault("accepted_campaign_names", [])
    return state


def canonical_campaign_name_error(
    config: RunnableConfig,
    campaign_name: str,
) -> str | None:
    """Reject a guessed campaign name after semantic resolution has begun."""

    state = _campaign_resolution_state(config)
    if int(state.get("attempts", 0)) == 0:
        return None
    requested = campaign_name.strip().casefold()
    accepted = {
        str(value).strip().casefold()
        for value in state.get("accepted_campaign_names") or []
    }
    if requested not in accepted:
        return "unverified_canonical_campaign"
    return None


@tool(args_schema=FindRealCampaignNameInput)
async def find_real_campaign_name(query: str, config: RunnableConfig) -> str:
    """Resolve a fuzzy campaign within the configured sequential-attempt policy."""

    tool_name = "find_real_campaign_name"
    state = _campaign_resolution_state(config)
    attempts = int(state.get("attempts", 0))
    agent_name = str(config.get("configurable", {}).get("agent_name") or "")
    accepted_campaign_names = [
        str(value) for value in state.get("accepted_campaign_names") or []
    ]
    if state.get("resolved") is True or accepted_campaign_names:
        state["resolved"] = True
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": tool_name,
                "result_status": "already_resolved",
                "error_type": "already_resolved",
                "error": (
                    "Canonical campaign names were already resolved. Reuse one or "
                    "more exact returned names and do not call this Tool again."
                ),
                "call_number": attempts,
                "max_attempts": MAX_CAMPAIGN_NAME_ATTEMPTS,
                "retryable": False,
                "terminal": True,
                "items": accepted_campaign_names,
            },
            ensure_ascii=False,
        )
    if state.get("in_flight") is True:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": tool_name,
                "result_status": "concurrent_query_blocked",
                "error_type": "concurrent_query_blocked",
                "error": "Campaign-name resolution calls must run sequentially.",
                "retryable": True,
                "terminal": False,
                "items": [],
            },
            ensure_ascii=False,
        )
    if attempts >= MAX_CAMPAIGN_NAME_ATTEMPTS:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": tool_name,
                "result_status": "canonical_campaign_not_found",
                "error_type": "canonical_campaign_not_found",
                "error": (
                    f"No canonical campaign name was found after {MAX_CAMPAIGN_NAME_ATTEMPTS} attempts. "
                    "Stop querying and ask the user for an exact campaign name."
                ),
                "call_number": attempts,
                "max_attempts": MAX_CAMPAIGN_NAME_ATTEMPTS,
                "retryable": False,
                "terminal": True,
                "items": [],
            },
            ensure_ascii=False,
        )

    call_number = attempts + 1
    minimum_similarity = CAMPAIGN_NAME_SIMILARITY_THRESHOLDS[attempts]
    state["attempts"] = call_number
    state["in_flight"] = True
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        call_number=call_number,
        query_length=len(query),
        top_k=CAMPAIGN_NAME_TOP_K,
        minimum_similarity=minimum_similarity,
        maximum_similarity_gap=MAX_SIMILARITY_GAP,
    )
    try:
        query_vector = await embedding_model.aembed_query(query)
        candidates = await asyncio.to_thread(
            _search_campaign_candidates,
            query_vector,
        )
        accepted = _filter_campaign_candidates(
            candidates,
            minimum_similarity=minimum_similarity,
        )
    except Exception as error:
        state["in_flight"] = False
        logger.exception(
            "tool.failed",
            error,
            component="tool",
            tool_name=tool_name,
        )
        raise RuntimeError(
            "Campaign-name semantic lookup is temporarily unavailable."
        ) from error

    campaign_names = [str(candidate["campaign_name"]) for candidate in accepted]
    state["in_flight"] = False
    existing = [
        str(value) for value in state.get("accepted_campaign_names") or []
    ]
    seen = {value.casefold() for value in existing}
    for campaign_name in campaign_names:
        if campaign_name.casefold() not in seen:
            existing.append(campaign_name)
            seen.add(campaign_name.casefold())
    state["accepted_campaign_names"] = existing
    state["resolved"] = bool(existing)
    terminal = not campaign_names and call_number >= MAX_CAMPAIGN_NAME_ATTEMPTS
    result_status = (
        "matched"
        if campaign_names
        else "canonical_campaign_not_found" if terminal else "no_match_retryable"
    )
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        call_number=call_number,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=bool(campaign_names),
        candidate_count=len(candidates),
        accepted_count=len(campaign_names),
        minimum_similarity=minimum_similarity,
        top_similarity=(
            round(float(candidates[0]["similarity"]), 6) if candidates else None
        ),
    )
    if campaign_names:
        return json.dumps(
            {
                "success": True,
                "agent": agent_name,
                "tool": tool_name,
                "result_status": "matched",
                "call_number": call_number,
                "max_attempts": MAX_CAMPAIGN_NAME_ATTEMPTS,
                "minimum_similarity": minimum_similarity,
                "retryable": False,
                "terminal": True,
                "items": campaign_names,
                "accepted_campaign_names": existing,
            },
            ensure_ascii=False,
        )

    payload = {
        "success": False,
        "agent": agent_name,
        "tool": tool_name,
        "result_status": result_status,
        "call_number": call_number,
        "max_attempts": MAX_CAMPAIGN_NAME_ATTEMPTS,
        "minimum_similarity": minimum_similarity,
        "retryable": not terminal,
        "terminal": terminal,
        "items": [],
    }
    payload["error_type"] = result_status
    payload["error"] = (
        "No canonical campaign name matched this attempt; retry with a faithful "
        "rephrasing of the user's campaign wording."
        if not terminal
        else (
            f"No canonical campaign name was found after {MAX_CAMPAIGN_NAME_ATTEMPTS} attempts. "
            "Stop querying and ask the user for an exact campaign name."
        )
    )
    return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "CAMPAIGN_NAME_SEARCH_SQL",
    "CAMPAIGN_NAME_SIMILARITY_THRESHOLDS",
    "CAMPAIGN_NAME_TOP_K",
    "FindRealCampaignNameInput",
    "MAX_CAMPAIGN_NAME_ATTEMPTS",
    "MAX_SIMILARITY_GAP",
    "MIN_SIMILARITY",
    "canonical_campaign_name_error",
    "find_real_campaign_name",
]
