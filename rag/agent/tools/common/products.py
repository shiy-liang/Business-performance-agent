"""Shared semantic resolution of fuzzy product terms to stored product names."""

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

from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


PRODUCT_NAME_TOP_K = 5
MIN_SIMILARITY = 0.70
PRODUCT_NAME_SIMILARITY_THRESHOLDS = (0.70, 0.60, 0.55)
MAX_PRODUCT_NAME_ATTEMPTS = len(PRODUCT_NAME_SIMILARITY_THRESHOLDS)
MAX_SIMILARITY_GAP = 0.20

PRODUCT_NAME_SEARCH_SQL = """
SELECT
    product_id,
    product_name,
    product_category,
    1 - (embedding <=> %(query_embedding)s) AS similarity
FROM public.products
WHERE embedding IS NOT NULL
  AND vector_dims(embedding) = %(dimensions)s
ORDER BY similarity DESC, product_name ASC
LIMIT 5
"""


class FindRealNameInput(BaseModel):
    """One natural-language product phrase supplied by the caller."""

    query: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "A fuzzy, non-standard, or cross-language product name from the user."
        ),
    )


def _search_product_candidates(query_vector: list[float]) -> list[dict[str, Any]]:
    """Execute the fixed Top-5 pgvector query in a read-only transaction."""

    vector = Vector(query_vector)
    with connect_readonly() as connection:
        with connection.cursor() as guard_cursor:
            set_readonly_guards(guard_cursor)
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                PRODUCT_NAME_SEARCH_SQL,
                {
                    "query_embedding": vector,
                    "dimensions": len(query_vector),
                },
            )
            rows = cursor.fetchall()

    return [
        {
            "product_id": row[0],
            "product_name": row[1],
            "product_category": row[2],
            "similarity": float(row[3]),
        }
        for row in rows
    ]


def _filter_product_candidates(
    candidates: list[dict[str, Any]],
    minimum_similarity: float = MIN_SIMILARITY,
) -> list[dict[str, Any]]:
    """Apply the absolute threshold and adjacent-score gap cutoff in rank order."""

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


def _product_resolution_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("product_resolution_runtime_state")
    if not isinstance(state, dict):
        state = {
            "attempts": 0,
            "in_flight": False,
            "accepted_product_names": [],
        }
        configurable["product_resolution_runtime_state"] = state
    state.setdefault("attempts", 0)
    state.setdefault("in_flight", False)
    state.setdefault("accepted_product_names", [])
    return state


def canonical_product_name_error(
    config: RunnableConfig,
    product_name: str,
) -> str | None:
    """Reject a guessed name after canonical resolution has already begun."""

    state = _product_resolution_state(config)
    if int(state.get("attempts", 0)) == 0:
        return None
    requested = product_name.strip().casefold()
    accepted = {
        str(value).strip().casefold()
        for value in state.get("accepted_product_names") or []
    }
    if requested not in accepted:
        return "unverified_canonical_product"
    return None


@tool(args_schema=FindRealNameInput)
async def find_real_name(query: str, config: RunnableConfig) -> str:
    """Resolve a fuzzy product in at most three sequential, progressively broader attempts."""

    tool_name = "find_real_name"
    state = _product_resolution_state(config)
    attempts = int(state.get("attempts", 0))
    agent_name = str(config.get("configurable", {}).get("agent_name") or "")
    if state.get("in_flight") is True:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": tool_name,
                "result_status": "concurrent_query_blocked",
                "error_type": "concurrent_query_blocked",
                "error": "Product-name resolution calls must run sequentially.",
                "retryable": True,
                "terminal": False,
                "items": [],
            },
            ensure_ascii=False,
        )
    if attempts >= MAX_PRODUCT_NAME_ATTEMPTS:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": tool_name,
                "result_status": "canonical_product_not_found",
                "error_type": "canonical_product_not_found",
                "error": (
                    "No canonical product name was found after three attempts. "
                    "Stop querying and ask the user for an exact product name."
                ),
                "call_number": attempts,
                "max_attempts": MAX_PRODUCT_NAME_ATTEMPTS,
                "retryable": False,
                "terminal": True,
                "items": [],
            },
            ensure_ascii=False,
        )

    call_number = attempts + 1
    minimum_similarity = PRODUCT_NAME_SIMILARITY_THRESHOLDS[attempts]
    state["attempts"] = call_number
    state["in_flight"] = True
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        call_number=call_number,
        query_length=len(query),
        top_k=PRODUCT_NAME_TOP_K,
        minimum_similarity=minimum_similarity,
        maximum_similarity_gap=MAX_SIMILARITY_GAP,
    )
    try:
        query_vector = await embedding_model.aembed_query(query)
        candidates = await asyncio.to_thread(
            _search_product_candidates,
            query_vector,
        )
        accepted = _filter_product_candidates(
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
            "Product-name semantic lookup is temporarily unavailable."
        ) from error

    product_names = [str(candidate["product_name"]) for candidate in accepted]
    state["in_flight"] = False
    existing = [str(value) for value in state.get("accepted_product_names") or []]
    seen = {value.casefold() for value in existing}
    for product_name in product_names:
        if product_name.casefold() not in seen:
            existing.append(product_name)
            seen.add(product_name.casefold())
    state["accepted_product_names"] = existing
    terminal = not product_names and call_number >= MAX_PRODUCT_NAME_ATTEMPTS
    result_status = (
        "matched"
        if product_names
        else "canonical_product_not_found" if terminal else "no_match_retryable"
    )
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        call_number=call_number,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=bool(product_names),
        candidate_count=len(candidates),
        accepted_count=len(product_names),
        minimum_similarity=minimum_similarity,
        top_similarity=(
            round(float(candidates[0]["similarity"]), 6) if candidates else None
        ),
    )
    if product_names:
        # Preserve the established successful-result contract for existing callers.
        return json.dumps(product_names, ensure_ascii=False)

    payload = {
        "success": False,
        "agent": agent_name,
        "tool": tool_name,
        "result_status": result_status,
        "call_number": call_number,
        "max_attempts": MAX_PRODUCT_NAME_ATTEMPTS,
        "minimum_similarity": minimum_similarity,
        "retryable": not terminal,
        "terminal": terminal,
        "items": [],
    }
    payload["error_type"] = result_status
    payload["error"] = (
        "No canonical product name matched this attempt; retry with a faithful "
        "rephrasing of the user's product wording."
        if not terminal
        else (
            "No canonical product name was found after three attempts. "
            "Stop querying and ask the user for an exact product name."
        )
    )
    return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "FindRealNameInput",
    "MAX_PRODUCT_NAME_ATTEMPTS",
    "MAX_SIMILARITY_GAP",
    "MIN_SIMILARITY",
    "PRODUCT_NAME_SIMILARITY_THRESHOLDS",
    "PRODUCT_NAME_SEARCH_SQL",
    "PRODUCT_NAME_TOP_K",
    "canonical_product_name_error",
    "find_real_name",
]
