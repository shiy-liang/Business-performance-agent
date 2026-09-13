"""Customer review knowledge synchronization endpoint."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, HTTPException, status

from backend.database import connect
from rag.utils.structured_vector_store import (
    StructuredVectorStoreError,
    sync_customer_review_embeddings,
)


router = APIRouter(prefix="/api/knowledge/reviews", tags=["knowledge-reviews"])


@router.post("/sync")
async def sync_customer_reviews() -> dict[str, object]:
    """Embed and update every customer review that has no stored vector."""

    try:
        with connect() as connection:
            result = await sync_customer_review_embeddings(connection)
    except StructuredVectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Customer reviews could not be synchronized safely",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The customer review database update failed",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The customer review embedding request failed",
        ) from exc

    return {
        "status": "completed",
        "synced_count": result.synced_count,
        "embedding_dimensions": result.embedding_dimensions,
        "embedding_model": result.embedding_model,
        "message": (
            f"Synced {result.synced_count} customer reviews into the knowledge base"
        ),
    }
