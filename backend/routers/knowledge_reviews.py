"""Customer review and support ticket knowledge synchronization endpoint."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, HTTPException, status

from backend.database import connect
from rag.utils.structured_vector_store import (
    StructuredVectorStoreError,
    sync_customer_review_embeddings,
    sync_support_ticket_embeddings,
)


router = APIRouter(prefix="/api/knowledge/reviews", tags=["knowledge-reviews"])


@router.post("/sync")
async def sync_customer_reviews() -> dict[str, object]:
    """Embed and update customer reviews and support tickets lacking vectors."""

    try:
        with connect() as connection:
            reviews_result = await sync_customer_review_embeddings(connection)
            tickets_result = await sync_support_ticket_embeddings(connection)
    except StructuredVectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Knowledge rows could not be synchronized safely",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge database update failed",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The knowledge embedding request failed",
        ) from exc

    return {
        "status": "completed",
        "synced_count": (
            reviews_result.synced_count + tickets_result.synced_count
        ),
        "reviews_synced_count": reviews_result.synced_count,
        "tickets_synced_count": tickets_result.synced_count,
        "embedding_dimensions": reviews_result.embedding_dimensions,
        "embedding_model": reviews_result.embedding_model,
        "message": (
            f"Synced {reviews_result.synced_count} customer reviews and "
            f"{tickets_result.synced_count} support tickets into the knowledge base"
        ),
    }
