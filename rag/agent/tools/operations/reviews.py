"""Deterministic retrieval tools for structured customer review rows."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from time import perf_counter
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field, model_validator

from config.settings import load_agent_settings
from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


_REVIEW_SETTINGS = load_agent_settings().review_retrieval
MAX_SEMANTIC_REVIEW_CALLS = _REVIEW_SETTINGS.max_semantic_calls_per_subtask
MAX_OTHER_COMMENT_CALLS = _REVIEW_SETTINGS.max_expansion_calls_per_subtask

OTHER_PRODUCT_COMMENTS_SQL = """
SELECT
    review_id,
    product_name,
    product_category,
    transaction_date,
    review_date,
    rating,
    review_title,
    review_text
FROM public.customer_reviews
WHERE LOWER(product_name) = LOWER(%(product_name)s::text)
  AND rating < %(rating)s::numeric
  AND NOT (review_id = ANY(%(excluded_review_ids)s::text[]))
ORDER BY review_date DESC, review_id
LIMIT %(result_limit)s
"""

OTHER_CATEGORY_COMMENTS_SQL = """
SELECT
    review_id,
    product_name,
    product_category,
    transaction_date,
    review_date,
    rating,
    review_title,
    review_text
FROM public.customer_reviews
WHERE LOWER(product_category) = LOWER(%(product_category)s::text)
  AND rating < %(rating)s::numeric
  AND NOT (review_id = ANY(%(excluded_review_ids)s::text[]))
ORDER BY review_date DESC, review_id
LIMIT %(result_limit)s
"""


def _minimum_similarity() -> float:
    return _REVIEW_SETTINGS.min_similarity


class ReviewSearchInput(BaseModel):
    query: str = Field(
        min_length=_REVIEW_SETTINGS.min_query_length,
        max_length=_REVIEW_SETTINGS.max_query_length,
        description="A concise description of the customer feedback theme to find.",
    )
    start_date: date | None = Field(
        default=None,
        description="Optional inclusive review-date lower bound.",
    )
    end_date: date | None = Field(
        default=None,
        description="Optional exclusive review-date upper bound.",
    )
    product_name: str | None = Field(
        default=None,
        max_length=_REVIEW_SETTINGS.max_scope_value_length,
    )
    product_category: str | None = Field(
        default=None,
        max_length=_REVIEW_SETTINGS.max_scope_value_length,
    )
    comparison_mode: bool = Field(
        default=False,
        description="True only when the user explicitly requests a comparison across products.",
    )
    min_rating: int | None = Field(default=None, ge=1, le=5)
    max_rating: int | None = Field(default=None, ge=1, le=5)
    top_k: int = Field(
        default=_REVIEW_SETTINGS.default_top_k,
        ge=1,
        le=_REVIEW_SETTINGS.max_top_k,
    )

    @model_validator(mode="after")
    def validate_ranges(self) -> "ReviewSearchInput":
        if not self.product_name and not self.product_category:
            raise ValueError(
                "product_name or product_category is required for customer-review search"
            )
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must be earlier than end_date")
        if (
            self.min_rating is not None
            and self.max_rating is not None
            and self.min_rating > self.max_rating
        ):
            raise ValueError("min_rating must not exceed max_rating")
        return self


class OtherProductCommentInput(BaseModel):
    product_name: str = Field(
        min_length=1,
        max_length=_REVIEW_SETTINGS.max_scope_value_length,
        description="One exact product_name selected from search_customer_reviews.",
    )
    rating: float = Field(
        default=_REVIEW_SETTINGS.default_expansion_rating_threshold,
        ge=1,
        le=5,
        description="Return reviews whose rating is strictly below this threshold.",
    )


class OtherCategoryCommentInput(BaseModel):
    product_category: str = Field(
        min_length=1,
        max_length=_REVIEW_SETTINGS.max_scope_value_length,
        description="One exact product_category selected from search_customer_reviews.",
    )
    rating: float = Field(
        default=_REVIEW_SETTINGS.default_expansion_rating_threshold,
        ge=1,
        le=5,
        description="Return reviews whose rating is strictly below this threshold.",
    )


def _review_runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("review_runtime_state")
    if not isinstance(state, dict):
        state = {
            "semantic_calls": 0,
            "semantic_in_flight": False,
            "other_comment_calls": 0,
            "other_comment_in_flight": False,
            "review_ids": [],
            "primary_product_name": None,
            "primary_product_category": None,
            "comparison_mode": False,
        }
        configurable["review_runtime_state"] = state
    state.setdefault("semantic_calls", 0)
    state.setdefault("semantic_in_flight", False)
    state.setdefault("other_comment_calls", 0)
    state.setdefault("other_comment_in_flight", False)
    state.setdefault("review_ids", [])
    state.setdefault("primary_product_name", None)
    state.setdefault("primary_product_category", None)
    state.setdefault("comparison_mode", False)
    return state


def _claim_review_call(
    config: RunnableConfig,
    *,
    kind: Literal["semantic", "other_comment"],
) -> tuple[str, int]:
    state = _review_runtime_state(config)
    calls_key = "semantic_calls" if kind == "semantic" else "other_comment_calls"
    in_flight_key = (
        "semantic_in_flight" if kind == "semantic" else "other_comment_in_flight"
    )
    maximum = (
        MAX_SEMANTIC_REVIEW_CALLS if kind == "semantic" else MAX_OTHER_COMMENT_CALLS
    )
    calls = int(state.get(calls_key, 0))
    if state.get(in_flight_key) is True:
        return "concurrent_query_blocked", calls
    if calls >= maximum:
        return "attempt_limit", calls
    state[calls_key] = calls + 1
    state[in_flight_key] = True
    return "permitted", calls + 1


def _finish_review_call(
    config: RunnableConfig,
    *,
    kind: Literal["semantic", "other_comment"],
    matches: list[dict[str, Any]],
) -> None:
    state = _review_runtime_state(config)
    in_flight_key = (
        "semantic_in_flight" if kind == "semantic" else "other_comment_in_flight"
    )
    state[in_flight_key] = False
    existing = [str(value) for value in state.get("review_ids") or []]
    seen = set(existing)
    for match in matches:
        review_id = str(match.get("review_id") or "")
        if review_id and review_id not in seen:
            seen.add(review_id)
            existing.append(review_id)
    state["review_ids"] = existing


def _seen_review_ids(config: RunnableConfig) -> list[str]:
    state = _review_runtime_state(config)
    return [str(value) for value in state.get("review_ids") or []]


def _normalized(value: str | None) -> str:
    return (value or "").strip().casefold()


def _claim_semantic_scope(
    config: RunnableConfig,
    inputs: ReviewSearchInput,
) -> str | None:
    """Lock review retrieval to one product unless comparison was explicit."""

    state = _review_runtime_state(config)
    calls = int(state.get("semantic_calls", 0))
    if calls == 0:
        state["primary_product_name"] = inputs.product_name
        state["primary_product_category"] = inputs.product_category
        state["comparison_mode"] = inputs.comparison_mode
        return None

    comparison_mode = state.get("comparison_mode") is True
    if inputs.comparison_mode and not comparison_mode:
        return "comparison_not_authorized"
    primary_product = _normalized(state.get("primary_product_name"))
    primary_category = _normalized(state.get("primary_product_category"))
    requested_product = _normalized(inputs.product_name)
    requested_category = _normalized(inputs.product_category)
    if not comparison_mode:
        if primary_product and requested_product != primary_product:
            return "product_scope_violation"
        if primary_product and requested_category:
            return "product_scope_violation"
        if primary_category and requested_category != primary_category:
            return "product_scope_violation"
        if primary_category and requested_product:
            return "product_scope_violation"
    return None


def _other_comment_scope_error(
    config: RunnableConfig,
    *,
    scope: Literal["product", "category"],
    value: str,
) -> str | None:
    state = _review_runtime_state(config)
    if state.get("comparison_mode") is True:
        return None
    primary_product = _normalized(state.get("primary_product_name"))
    primary_category = _normalized(state.get("primary_product_category"))
    requested = _normalized(value)
    if scope == "product":
        if primary_product and requested == primary_product:
            return None
        return "product_scope_violation"
    if primary_category and requested == primary_category:
        return None
    return "product_scope_violation"


def _blocked_payload(tool_name: str, error_type: str, maximum: int) -> str:
    if error_type == "concurrent_query_blocked":
        error = "Another customer-review retrieval is already running; parallel calls are not allowed."
    elif error_type == "attempt_limit":
        error = (
            f"The maximum of {maximum} calls for this customer-review retrieval "
            "step in the current subtask was reached."
        )
    elif error_type == "comparison_not_authorized":
        error = "Additional products cannot be queried because the original request did not ask for a comparison."
    else:
        error = "The requested review scope would query another product without an explicit comparison request."
    return json.dumps(
        {
            "success": False,
            "agent": "operations",
            "tool": tool_name,
            "evidence_kind": "customer_review",
            "error_type": error_type,
            "error": error,
            "retryable": False,
            "matches": [],
            "sources": [],
        },
        ensure_ascii=False,
    )


def _search_reviews(
    query_vector: list[float],
    filters: ReviewSearchInput,
    excluded_review_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    vector = Vector(query_vector)
    threshold = _minimum_similarity()
    parameters = {
        "vector": vector,
        "dimensions": len(query_vector),
        "start_date": filters.start_date,
        "end_date": filters.end_date,
        "product_name": filters.product_name,
        "product_category": filters.product_category,
        "min_rating": filters.min_rating,
        "max_rating": filters.max_rating,
        "minimum_similarity": threshold,
        "excluded_review_ids": excluded_review_ids or [],
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
                    review_id,
                    product_name,
                    product_category,
                    review_date,
                    rating,
                    review_title,
                    review_text,
                    1 - (embedding <=> %(vector)s) AS similarity
                FROM public.customer_reviews
                WHERE embedding IS NOT NULL
                  AND vector_dims(embedding) = %(dimensions)s
                  AND (%(start_date)s::date IS NULL OR review_date >= %(start_date)s::date)
                  AND (%(end_date)s::date IS NULL OR review_date < %(end_date)s::date)
                  AND (%(min_rating)s::integer IS NULL OR rating >= %(min_rating)s::integer)
                  AND (%(max_rating)s::integer IS NULL OR rating <= %(max_rating)s::integer)
                  AND NOT (review_id = ANY(%(excluded_review_ids)s::text[]))
                  AND 1 - (embedding <=> %(vector)s) >= %(minimum_similarity)s
                ORDER BY embedding <=> %(vector)s, review_date DESC, review_id
                LIMIT %(top_k)s
                """,
                parameters,
            )
            rows = cursor.fetchall()

    return [
        {
            "review_id": row[0],
            "product_name": row[1],
            "product_category": row[2],
            "review_date": row[3].isoformat(),
            "rating": row[4],
            "review_title": row[5],
            "review_text": row[6],
            "similarity": round(float(row[7]), 6),
            "citation": f"[review:{row[0]}]",
        }
        for row in rows
    ]


def _find_other_comments(
    *,
    scope: Literal["product", "category"],
    value: str,
    rating: float,
    excluded_review_ids: list[str],
) -> list[dict[str, Any]]:
    sql = OTHER_PRODUCT_COMMENTS_SQL if scope == "product" else OTHER_CATEGORY_COMMENTS_SQL
    scope_parameter = "product_name" if scope == "product" else "product_category"
    parameters = {
        scope_parameter: value,
        "rating": rating,
        "excluded_review_ids": excluded_review_ids,
        "result_limit": _REVIEW_SETTINGS.expansion_result_limit,
    }
    with connect_readonly() as connection:
        with connection.cursor() as guard_cursor:
            set_readonly_guards(guard_cursor)
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            rows = cursor.fetchall()

    return [
        {
            "review_id": row[0],
            "product_name": row[1],
            "product_category": row[2],
            "transaction_date": row[3].isoformat(),
            "review_date": row[4].isoformat(),
            "rating": row[5],
            "review_title": row[6],
            "review_text": row[7],
            "citation": f"[review:{row[0]}]",
        }
        for row in rows
    ]


def _review_sources(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "customer_review",
            "filename": f"Customer review · {match['product_name']}",
            "review_id": match["review_id"],
            "citation": match["citation"],
            **(
                {"similarity": match["similarity"]}
                if "similarity" in match
                else {}
            ),
        }
        for match in matches
    ]


@tool(args_schema=ReviewSearchInput)
async def search_customer_reviews(
    query: str,
    config: RunnableConfig,
    start_date: date | None = None,
    end_date: date | None = None,
    product_name: str | None = None,
    product_category: str | None = None,
    comparison_mode: bool = False,
    min_rating: int | None = None,
    max_rating: int | None = None,
    top_k: int = _REVIEW_SETTINGS.default_top_k,
) -> str:
    """Search reviews for one filtered product; repeat only for complex or comparative tasks."""

    tool_name = "search_customer_reviews"
    inputs = ReviewSearchInput(
        query=query,
        start_date=start_date,
        end_date=end_date,
        product_name=product_name,
        product_category=product_category,
        comparison_mode=comparison_mode,
        min_rating=min_rating,
        max_rating=max_rating,
        top_k=top_k,
    )
    scope_error = _claim_semantic_scope(config, inputs)
    if scope_error:
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type=scope_error,
            call_number=int(_review_runtime_state(config).get("semantic_calls", 0)),
        )
        return _blocked_payload(tool_name, scope_error, MAX_SEMANTIC_REVIEW_CALLS)

    claim_status, call_number = _claim_review_call(config, kind="semantic")
    if claim_status != "permitted":
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type=claim_status,
            call_number=call_number,
        )
        return _blocked_payload(tool_name, claim_status, MAX_SEMANTIC_REVIEW_CALLS)
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
                product_name,
                product_category,
                min_rating,
                max_rating,
            )
        ),
    )
    matches: list[dict[str, Any]] = []
    try:
        query_vector = await embedding_model.aembed_query(query)
        excluded_review_ids = _seen_review_ids(config)
        if excluded_review_ids:
            matches = await asyncio.to_thread(
                _search_reviews,
                query_vector,
                inputs,
                excluded_review_ids,
            )
        else:
            matches = await asyncio.to_thread(_search_reviews, query_vector, inputs)
    except Exception as error:
        _finish_review_call(config, kind="semantic", matches=[])
        logger.exception(
            "tool.failed",
            error,
            component="tool",
            tool_name=tool_name,
        )
        return json.dumps(
            {
                "success": False,
                "agent": "operations",
                "tool": tool_name,
                "evidence_kind": "customer_review",
                "error_type": "retrieval_error",
                "error": "Customer-review semantic evidence is temporarily unavailable.",
                "query": query,
                "filters": inputs.model_dump(mode="json", exclude={"query", "top_k"}),
                "matches": [],
                "sources": [],
            },
            ensure_ascii=False,
        )

    _finish_review_call(config, kind="semantic", matches=matches)
    sources = _review_sources(matches)
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=True,
        call_number=call_number,
        top_k=top_k,
        match_count=len(matches),
        minimum_similarity=_minimum_similarity(),
    )
    return json.dumps(
        {
            "success": True,
            "agent": "operations",
            "tool": tool_name,
            "evidence_kind": "customer_review",
            "call_number": call_number,
            "query": query,
            "filters": inputs.model_dump(mode="json", exclude={"query", "top_k"}),
            "minimum_similarity": _minimum_similarity(),
            "matches": matches,
            "sources": sources,
        },
        ensure_ascii=False,
        default=str,
    )


async def _run_other_comment_tool(
    *,
    tool_name: str,
    scope: Literal["product", "category"],
    value: str,
    rating: float,
    config: RunnableConfig,
) -> str:
    scope_error = _other_comment_scope_error(
        config,
        scope=scope,
        value=value,
    )
    if scope_error:
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type=scope_error,
            call_number=int(
                _review_runtime_state(config).get("other_comment_calls", 0)
            ),
        )
        return _blocked_payload(tool_name, scope_error, MAX_OTHER_COMMENT_CALLS)

    claim_status, call_number = _claim_review_call(config, kind="other_comment")
    if claim_status != "permitted":
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            success=False,
            error_type=claim_status,
            call_number=call_number,
        )
        return _blocked_payload(tool_name, claim_status, MAX_OTHER_COMMENT_CALLS)

    started_at = perf_counter()
    excluded_review_ids = _seen_review_ids(config)
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        call_number=call_number,
        rating_threshold=rating,
        excluded_review_count=len(excluded_review_ids),
    )
    matches: list[dict[str, Any]] = []
    try:
        matches = await asyncio.to_thread(
            _find_other_comments,
            scope=scope,
            value=value,
            rating=rating,
            excluded_review_ids=excluded_review_ids,
        )
    except Exception as error:
        _finish_review_call(config, kind="other_comment", matches=[])
        logger.exception("tool.failed", error, component="tool", tool_name=tool_name)
        return json.dumps(
            {
                "success": False,
                "agent": "operations",
                "tool": tool_name,
                "evidence_kind": "customer_review",
                "error_type": "retrieval_error",
                "error": "Additional customer reviews are temporarily unavailable.",
                "matches": [],
                "sources": [],
            },
            ensure_ascii=False,
        )

    _finish_review_call(config, kind="other_comment", matches=matches)
    sources = _review_sources(matches)
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=True,
        call_number=call_number,
        match_count=len(matches),
        rating_threshold=rating,
    )
    filter_name = "product_name" if scope == "product" else "product_category"
    return json.dumps(
        {
            "success": True,
            "agent": "operations",
            "tool": tool_name,
            "evidence_kind": "customer_review",
            "call_number": call_number,
            "filters": {filter_name: value, "rating_below": rating},
            "excluded_review_count": len(excluded_review_ids),
            "matches": matches,
            "sources": sources,
        },
        ensure_ascii=False,
        default=str,
    )


@tool(args_schema=OtherProductCommentInput)
async def find_other_comment_product(
    product_name: str,
    config: RunnableConfig,
    rating: float = _REVIEW_SETTINGS.default_expansion_rating_threshold,
) -> str:
    """Find unseen reviews for one product below a rating threshold."""

    return await _run_other_comment_tool(
        tool_name="find_other_comment_product",
        scope="product",
        value=product_name,
        rating=rating,
        config=config,
    )


@tool(args_schema=OtherCategoryCommentInput)
async def find_other_comment_category(
    product_category: str,
    config: RunnableConfig,
    rating: float = _REVIEW_SETTINGS.default_expansion_rating_threshold,
) -> str:
    """Find unseen reviews for one product category below a rating threshold."""

    return await _run_other_comment_tool(
        tool_name="find_other_comment_category",
        scope="category",
        value=product_category,
        rating=rating,
        config=config,
    )


__all__ = [
    "MAX_OTHER_COMMENT_CALLS",
    "MAX_SEMANTIC_REVIEW_CALLS",
    "OtherCategoryCommentInput",
    "OtherProductCommentInput",
    "ReviewSearchInput",
    "find_other_comment_category",
    "find_other_comment_product",
    "search_customer_reviews",
]
