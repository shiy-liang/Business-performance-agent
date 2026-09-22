"""Load uploaded files, create embeddings, and store knowledge chunks."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import psycopg
from langchain_community.document_loaders import CSVLoader, TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pgvector import Vector
from pgvector.psycopg import register_vector

from model import embedding_model
from observability import logger
from rag.utils.config import RagConfig, load_rag_config


SOURCE_TYPE = "other"


class KnowledgeIngestionError(RuntimeError):
    """Raised when a file cannot be converted into stored knowledge chunks."""


@dataclass(frozen=True, slots=True)
class KnowledgeIngestionResult:
    source_type: str
    source_id: str
    chunk_count: int
    embedding_dimensions: int
    embedding_model: str


def _calculate_sha256(file_path: Path, stream_chunk_size_bytes: int) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        while chunk := source.read(stream_chunk_size_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _document_loader(file_path: Path, extension: str) -> Any:
    if extension == ".csv":
        return CSVLoader(
            file_path=str(file_path),
            encoding="utf-8",
            autodetect_encoding=True,
        )
    if extension == ".txt":
        return TextLoader(
            file_path=str(file_path),
            encoding="utf-8",
            autodetect_encoding=True,
        )
    if extension == ".pdf":
        return PyPDFLoader(file_path=str(file_path))
    raise KnowledgeIngestionError(f"No document loader is configured for {extension}")


def _load_and_split(file_path: Path, extension: str, config: RagConfig) -> list[str]:
    loader = _document_loader(file_path, extension)
    documents = list(loader.lazy_load())
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.document_processing.chunk_size,
        chunk_overlap=config.document_processing.chunk_overlap,
        separators=list(config.document_processing.separators),
        length_function=len,
        is_separator_regex=False,
    )
    split_documents = splitter.split_documents(documents)
    chunks = [document.page_content.strip() for document in split_documents]
    chunks = [content for content in chunks if content]
    if not chunks:
        raise KnowledgeIngestionError("The file does not contain readable text")
    return chunks


def _embedding_dimensions(vectors: list[list[float]], expected: int | None) -> int:
    if not vectors or not vectors[0]:
        raise KnowledgeIngestionError("The embedding model returned no vectors")
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise KnowledgeIngestionError("The embedding vectors have inconsistent dimensions")
    if expected is not None and dimensions != expected:
        raise KnowledgeIngestionError(
            f"Expected {expected} embedding dimensions but received {dimensions}"
        )
    return dimensions


def _store_chunks(
    connection: psycopg.Connection,
    source_id: str,
    chunks: list[str],
    vectors: list[list[float]],
) -> None:
    register_vector(connection)
    rows = [
        (SOURCE_TYPE, source_id, index, content, Vector(vector))
        for index, (content, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO unstructured_knowledge_chunks (
                source_type, source_id, chunk_index, content, embedding
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_type, source_id, chunk_index) DO UPDATE SET
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = '{}'::jsonb
            """,
            rows,
        )
        cursor.execute(
            """
            DELETE FROM unstructured_knowledge_chunks
            WHERE source_type = %s
              AND source_id = %s
              AND chunk_index >= %s
            """,
            (SOURCE_TYPE, source_id, len(chunks)),
        )


async def ingest_knowledge_file(
    connection: psycopg.Connection,
    *,
    file_id: int,
    file_path: Path,
    original_filename: str,
    file_hash: str,
    extension: str,
    embedding_client: Any | None = None,
) -> KnowledgeIngestionResult:
    """Load, split, embed, and store one previously validated source file."""

    started_at = perf_counter()
    source_id = str(file_id)
    config = load_rag_config()
    active_embedding_model = embedding_client or embedding_model
    logger.info(
        "knowledge_ingestion.started",
        component="knowledge_ingestion",
        source_type=SOURCE_TYPE,
        source_id=source_id,
        original_filename=original_filename,
    )

    try:
        persisted_hash = await asyncio.to_thread(
            _calculate_sha256,
            file_path,
            config.file_upload.stream_chunk_size_bytes,
        )
        if persisted_hash != file_hash:
            raise KnowledgeIngestionError(
                "The persisted file hash does not match the validated upload hash"
            )

        chunks = await asyncio.to_thread(
            _load_and_split,
            file_path,
            extension,
            config,
        )
        vectors = await active_embedding_model.aembed_documents(chunks)
        if len(vectors) != len(chunks):
            raise KnowledgeIngestionError(
                "The embedding count does not match the document chunk count"
            )
        expected_dimensions = getattr(active_embedding_model.settings, "dimensions", None)
        dimensions = _embedding_dimensions(vectors, expected_dimensions)
        await asyncio.to_thread(
            _store_chunks,
            connection,
            source_id,
            chunks,
            vectors,
        )
    except Exception as error:
        logger.exception(
            "knowledge_ingestion.failed",
            error,
            component="knowledge_ingestion",
            source_type=SOURCE_TYPE,
            source_id=source_id,
            original_filename=original_filename,
        )
        raise

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    model_name = str(active_embedding_model.settings.model)
    logger.info(
        "knowledge_ingestion.completed",
        component="knowledge_ingestion",
        source_type=SOURCE_TYPE,
        source_id=source_id,
        original_filename=original_filename,
        chunk_count=len(chunks),
        embedding_dimensions=dimensions,
        embedding_model=model_name,
        duration_ms=duration_ms,
    )
    return KnowledgeIngestionResult(
        source_type=SOURCE_TYPE,
        source_id=source_id,
        chunk_count=len(chunks),
        embedding_dimensions=dimensions,
        embedding_model=model_name,
    )


__all__ = [
    "KnowledgeIngestionError",
    "KnowledgeIngestionResult",
    "SOURCE_TYPE",
    "ingest_knowledge_file",
]
