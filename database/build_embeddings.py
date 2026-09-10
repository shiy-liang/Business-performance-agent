"""Generate free local multilingual embeddings and save them to pgvector."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EXPECTED_DIMENSIONS = 384


def settings() -> tuple[str, str, int]:
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is missing from .env")
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
    batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
    return url, model, batch_size


def fetch_documents(connection: psycopg.Connection) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT review_id, customer_id, product_name, product_category,
                      rating, review_title, review_text
               FROM customer_reviews ORDER BY review_id"""
        )
        for review_id, customer_id, product, category, rating, title, body in cursor:
            content = (
                f"Customer review. Product: {product}. Category: {category}. "
                f"Rating: {rating} out of 5. Title: {title or ''}. "
                f"Review: {body or ''}"
            )
            documents.append({
                "source_type": "customer_review", "source_id": review_id,
                "customer_id": customer_id, "content": content,
                "metadata": {"product_name": product, "product_category": category,
                             "rating": rating},
            })

        cursor.execute(
            """SELECT ticket_id, customer_id, issue_category, priority,
                      resolution_status, notes
               FROM support_tickets ORDER BY ticket_id"""
        )
        for ticket_id, customer_id, category, priority, status, notes in cursor:
            content = (
                f"Support ticket. Issue: {category}. Priority: {priority}. "
                f"Status: {status}. Notes: {notes or ''}"
            )
            documents.append({
                "source_type": "support_ticket", "source_id": ticket_id,
                "customer_id": customer_id, "content": content,
                "metadata": {"issue_category": category, "priority": priority,
                             "resolution_status": status},
            })
    return documents


def main() -> None:
    url, model_name, batch_size = settings()
    model = SentenceTransformer(model_name)
    with psycopg.connect(url, autocommit=False) as connection:
        register_vector(connection)
        documents = fetch_documents(connection)
        if not documents:
            raise RuntimeError("No source rows found. Run database/load_data.py first.")

        embeddings = np.asarray(model.encode(
            [str(document["content"]) for document in documents],
            batch_size=batch_size, normalize_embeddings=True, show_progress_bar=True,
        ), dtype=np.float32)
        if embeddings.shape != (len(documents), EXPECTED_DIMENSIONS):
            raise ValueError(
                f"Expected 384-dimensional vectors, received {embeddings.shape}."
            )

        rows = [(
            document["source_type"], document["source_id"], document["customer_id"],
            document["content"], Jsonb(document["metadata"]), model_name, embedding,
        ) for document, embedding in zip(documents, embeddings, strict=True)]

        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO business_documents
                   (source_type, source_id, customer_id, content, metadata,
                    embedding_model, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (source_type, source_id) DO UPDATE SET
                     customer_id=EXCLUDED.customer_id, content=EXCLUDED.content,
                     metadata=EXCLUDED.metadata, embedding_model=EXCLUDED.embedding_model,
                     embedding=EXCLUDED.embedding, created_at=NOW()""",
                rows,
            )
        connection.commit()
    print(f"Stored {len(documents)} embeddings using {model_name}.")


if __name__ == "__main__":
    main()
