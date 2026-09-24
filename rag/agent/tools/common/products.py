"""Shared semantic resolution of fuzzy product terms to stored product names."""

from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any

from langchain_core.tools import tool
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field

from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


PRODUCT_NAME_TOP_K = 5
MIN_SIMILARITY = 0.70
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
) -> list[dict[str, Any]]:
    """Apply the absolute threshold and adjacent-score gap cutoff in rank order."""

    accepted: list[dict[str, Any]] = []
    previous_similarity: float | None = None
    for candidate in candidates:
        similarity = float(candidate["similarity"])
        if similarity < MIN_SIMILARITY:
            break
        if (
            previous_similarity is not None
            and previous_similarity - similarity > MAX_SIMILARITY_GAP
        ):
            break
        accepted.append(candidate)
        previous_similarity = similarity
    return accepted


@tool(args_schema=FindRealNameInput)
async def find_real_name(query: str) -> str:
    """Map a fuzzy product phrase to ranked, exact public.products.product_name values."""

    tool_name = "find_real_name"
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        query_length=len(query),
        top_k=PRODUCT_NAME_TOP_K,
        minimum_similarity=MIN_SIMILARITY,
        maximum_similarity_gap=MAX_SIMILARITY_GAP,
    )
    try:
        query_vector = await embedding_model.aembed_query(query)
        candidates = await asyncio.to_thread(
            _search_product_candidates,
            query_vector,
        )
        accepted = _filter_product_candidates(candidates)
    except Exception as error:
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
    logger.tool_event(
        status="completed",
        tool_name=tool_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=True,
        candidate_count=len(candidates),
        accepted_count=len(product_names),
        top_similarity=(
            round(float(candidates[0]["similarity"]), 6) if candidates else None
        ),
    )
    return json.dumps(product_names, ensure_ascii=False)


__all__ = [
    "FindRealNameInput",
    "MAX_SIMILARITY_GAP",
    "MIN_SIMILARITY",
    "PRODUCT_NAME_SEARCH_SQL",
    "PRODUCT_NAME_TOP_K",
    "find_real_name",
]
