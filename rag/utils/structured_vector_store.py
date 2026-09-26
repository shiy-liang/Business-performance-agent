"""Create and store one semantic vector for each structured knowledge row."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Mapping

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from model import embedding_model
from observability import logger


class StructuredVectorStoreError(RuntimeError):
    """Raised when structured source vectors cannot be synchronized safely."""


@dataclass(frozen=True, slots=True)
class CustomerReviewSyncResult:
    synced_count: int
    embedding_dimensions: int | None
    embedding_model: str


@dataclass(frozen=True, slots=True)
class SupportTicketSyncResult:
    synced_count: int
    embedding_dimensions: int | None
    embedding_model: str


def _review_embedding_text(review: Mapping[str, Any]) -> str:
    title = review.get("review_title") or "Not provided"
    text = review.get("review_text") or "Not provided"
    return "\n".join(
        (
            f"Product: {review['product_name']}",
            f"Category: {review['product_category']}",
            f"Rating: {review['rating']}/5 (maximum score: 5)",
            f"Review title: {title}",
            f"Customer review: {text}",
        )
    )


def _fetch_pending_reviews(connection: psycopg.Connection) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT review_id, customer_id, product_name, product_category,
                   full_name, transaction_date, review_date, rating,
                   review_title, review_text
            FROM public.customer_reviews
            WHERE embedding IS NULL
            ORDER BY review_id
            FOR UPDATE
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _vector_dimensions(vectors: list[list[float]], expected: int | None) -> int:
    if not vectors or not vectors[0]:
        raise StructuredVectorStoreError("The embedding model returned no vectors")
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise StructuredVectorStoreError(
            "The embedding vectors have inconsistent dimensions"
        )
    if expected is not None and dimensions != expected:
        raise StructuredVectorStoreError(
            f"Expected {expected} embedding dimensions but received {dimensions}"
        )
    return dimensions


def _store_review_vectors(
    connection: psycopg.Connection,
    reviews: list[dict[str, Any]],
    vectors: list[list[float]],
) -> int:
    register_vector(connection)
    rows = [
        (Vector(vector), review["review_id"])
        for review, vector in zip(reviews, vectors, strict=True)
    ]
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            UPDATE public.customer_reviews
            SET embedding = %s
            WHERE review_id = %s AND embedding IS NULL
            """,
            rows,
        )
        updated_count = cursor.rowcount
    if updated_count != len(rows):
        raise StructuredVectorStoreError(
            "The updated customer review count does not match the embedding count"
        )
    return updated_count


async def sync_customer_review_embeddings(
    connection: psycopg.Connection,
    *,
    embedding_client: Any | None = None,
) -> CustomerReviewSyncResult:
    """Embed every customer review whose embedding column is currently null."""

    started_at = perf_counter()
    active_embedding_model = embedding_client or embedding_model
    model_name = str(active_embedding_model.settings.model)
    logger.info(
        "customer_review_sync.started",
        component="structured_vector_store",
        embedding_model=model_name,
    )

    try:
        reviews = await asyncio.to_thread(_fetch_pending_reviews, connection)
        if not reviews:
            dimensions = getattr(active_embedding_model.settings, "dimensions", None)
            synced_count = 0
        else:
            texts = [_review_embedding_text(review) for review in reviews]
            vectors = await active_embedding_model.aembed_documents(texts)
            if len(vectors) != len(reviews):
                raise StructuredVectorStoreError(
                    "The customer review embedding count does not match the review count"
                )
            expected_dimensions = getattr(
                active_embedding_model.settings,
                "dimensions",
                None,
            )
            dimensions = _vector_dimensions(vectors, expected_dimensions)
            synced_count = await asyncio.to_thread(
                _store_review_vectors,
                connection,
                reviews,
                vectors,
            )
    except Exception as error:
        logger.exception(
            "customer_review_sync.failed",
            error,
            component="structured_vector_store",
            embedding_model=model_name,
        )
        raise

    logger.info(
        "customer_review_sync.completed",
        component="structured_vector_store",
        synced_count=synced_count,
        embedding_dimensions=dimensions,
        embedding_model=model_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return CustomerReviewSyncResult(
        synced_count=synced_count,
        embedding_dimensions=dimensions,
        embedding_model=model_name,
    )


def _ticket_embedding_text(ticket: Mapping[str, Any]) -> str:
    resolution_time = ticket.get("resolution_time_hours")
    satisfaction_score = ticket.get("customer_satisfaction_score")
    return "\n".join(
        (
            f"Ticket issue category: {ticket['issue_category']}",
            f"Priority: {ticket['priority']}",
            f"Resolution status: {ticket['resolution_status']}",
            f"Resolution time: {resolution_time if resolution_time is not None else 'Not provided'} hours",
            f"Customer satisfaction score: "
            f"{satisfaction_score if satisfaction_score is not None else 'Not provided'}",
            f"Issue description: {ticket.get('notes') or 'Not provided'}",
        )
    )


def _fetch_pending_tickets(connection: psycopg.Connection) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT ticket_id, customer_id, issue_category, priority,
                   submission_date, resolution_date, resolution_status,
                   resolution_time_hours, customer_satisfaction_score, notes
            FROM public.support_tickets
            WHERE embedding IS NULL
            ORDER BY ticket_id
            FOR UPDATE
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _store_ticket_vectors(
    connection: psycopg.Connection,
    tickets: list[dict[str, Any]],
    vectors: list[list[float]],
) -> int:
    register_vector(connection)
    rows = [
        (Vector(vector), ticket["ticket_id"])
        for ticket, vector in zip(tickets, vectors, strict=True)
    ]
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            UPDATE public.support_tickets
            SET embedding = %s
            WHERE ticket_id = %s AND embedding IS NULL
            """,
            rows,
        )
        updated_count = cursor.rowcount
    if updated_count != len(rows):
        raise StructuredVectorStoreError(
            "The updated support ticket count does not match the embedding count"
        )
    return updated_count


async def sync_support_ticket_embeddings(
    connection: psycopg.Connection,
    *,
    embedding_client: Any | None = None,
) -> SupportTicketSyncResult:
    """Embed every support ticket whose embedding column is currently null."""

    started_at = perf_counter()
    active_embedding_model = embedding_client or embedding_model
    model_name = str(active_embedding_model.settings.model)
    logger.info(
        "support_ticket_sync.started",
        component="structured_vector_store",
        embedding_model=model_name,
    )

    try:
        tickets = await asyncio.to_thread(_fetch_pending_tickets, connection)
        if not tickets:
            dimensions = getattr(active_embedding_model.settings, "dimensions", None)
            synced_count = 0
        else:
            texts = [_ticket_embedding_text(ticket) for ticket in tickets]
            vectors = await active_embedding_model.aembed_documents(texts)
            if len(vectors) != len(tickets):
                raise StructuredVectorStoreError(
                    "The support ticket embedding count does not match the ticket count"
                )
            expected_dimensions = getattr(
                active_embedding_model.settings,
                "dimensions",
                None,
            )
            dimensions = _vector_dimensions(vectors, expected_dimensions)
            synced_count = await asyncio.to_thread(
                _store_ticket_vectors,
                connection,
                tickets,
                vectors,
            )
    except Exception as error:
        logger.exception(
            "support_ticket_sync.failed",
            error,
            component="structured_vector_store",
            embedding_model=model_name,
        )
        raise

    logger.info(
        "support_ticket_sync.completed",
        component="structured_vector_store",
        synced_count=synced_count,
        embedding_dimensions=dimensions,
        embedding_model=model_name,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return SupportTicketSyncResult(
        synced_count=synced_count,
        embedding_dimensions=dimensions,
        embedding_model=model_name,
    )


__all__ = [
    "CustomerReviewSyncResult",
    "StructuredVectorStoreError",
    "SupportTicketSyncResult",
    "sync_customer_review_embeddings",
    "sync_support_ticket_embeddings",
]
