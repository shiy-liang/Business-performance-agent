"""Filtered semantic retrieval over structured customer review rows."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from time import perf_counter
from typing import Any

from langchain_core.tools import tool
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field, model_validator

from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


def _minimum_similarity() -> float:
    try:
        value = float(os.getenv("AGENT_REVIEW_MIN_SIMILARITY", "0.25"))
    except ValueError:
        return 0.25
    return value if -1.0 <= value <= 1.0 else 0.25


class ReviewSearchInput(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=500,
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
    product_name: str | None = Field(default=None, max_length=200)
    product_category: str | None = Field(default=None, max_length=200)
    min_rating: int | None = Field(default=None, ge=1, le=5)
    max_rating: int | None = Field(default=None, ge=1, le=5)
    top_k: int = Field(default=5, ge=1, le=8)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ReviewSearchInput":
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must be earlier than end_date")
        if (
            self.min_rating is not None
            and self.max_rating is not None
            and self.min_rating > self.max_rating
        ):
            raise ValueError("min_rating must not exceed max_rating")
        return self


def _search_reviews(
    query_vector: list[float],
    filters: ReviewSearchInput,
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
                FROM customer_reviews
                WHERE embedding IS NOT NULL
                  AND vector_dims(embedding) = %(dimensions)s
                  AND (%(start_date)s::date IS NULL OR review_date >= %(start_date)s::date)
                  AND (%(end_date)s::date IS NULL OR review_date < %(end_date)s::date)
                  AND (
                        %(product_name)s::text IS NULL
                        OR LOWER(product_name) = LOWER(%(product_name)s::text)
                  )
                  AND (
                        %(product_category)s::text IS NULL
                        OR LOWER(product_category) = LOWER(%(product_category)s::text)
                  )
                  AND (%(min_rating)s::integer IS NULL OR rating >= %(min_rating)s::integer)
                  AND (%(max_rating)s::integer IS NULL OR rating <= %(max_rating)s::integer)
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


@tool(args_schema=ReviewSearchInput)
async def search_customer_reviews(
    query: str,
    start_date: date | None = None,
    end_date: date | None = None,
    product_name: str | None = None,
    product_category: str | None = None,
    min_rating: int | None = None,
    max_rating: int | None = None,
    top_k: int = 5,
) -> str:
    """Semantically search customer reviews after applying structured filters."""

    inputs = ReviewSearchInput(
        query=query,
        start_date=start_date,
        end_date=end_date,
        product_name=product_name,
        product_category=product_category,
        min_rating=min_rating,
        max_rating=max_rating,
        top_k=top_k,
    )
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name="search_customer_reviews",
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
    try:
        query_vector = await embedding_model.aembed_query(query)
        matches = await asyncio.to_thread(_search_reviews, query_vector, inputs)
    except Exception as error:
        logger.exception(
            "tool.failed",
            error,
            component="tool",
            tool_name="search_customer_reviews",
        )
        return json.dumps(
            {
                "success": False,
                "tool": "search_customer_reviews",
                "error_type": "retrieval_error",
                "error": "Customer-review semantic evidence is temporarily unavailable.",
                "query": query,
                "filters": inputs.model_dump(mode="json", exclude={"query", "top_k"}),
                "matches": [],
                "sources": [],
            },
            ensure_ascii=False,
        )

    sources = [
        {
            "type": "customer_review",
            "filename": f"Customer review · {match['product_name']}",
            "review_id": match["review_id"],
            "citation": match["citation"],
            "similarity": match["similarity"],
        }
        for match in matches
    ]
    logger.tool_event(
        status="completed",
        tool_name="search_customer_reviews",
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        top_k=top_k,
        match_count=len(matches),
        minimum_similarity=_minimum_similarity(),
    )
    return json.dumps(
        {
            "success": True,
            "tool": "search_customer_reviews",
            "query": query,
            "filters": inputs.model_dump(mode="json", exclude={"query", "top_k"}),
            "minimum_similarity": _minimum_similarity(),
            "matches": matches,
            "sources": sources,
        },
        ensure_ascii=False,
        default=str,
    )


__all__ = ["ReviewSearchInput", "search_customer_reviews"]
