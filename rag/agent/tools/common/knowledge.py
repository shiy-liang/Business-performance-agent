"""Supervisor-authorized retrieval over uploaded knowledge files."""

from __future__ import annotations

import asyncio
import json
import os
from time import perf_counter
from typing import Any

from langchain_core.tools import tool
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field

from model import embedding_model
from observability import logger
from rag.agent.tools.common.sql_runtime import connect_readonly, set_readonly_guards


class KnowledgeSearchInput(BaseModel):
    """Validated semantic search input exposed to the supervisor."""

    query: str = Field(
        min_length=2,
        max_length=500,
        description="A concise semantic search query preserving rule IDs and business entities.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=5,
        description="Maximum number of knowledge chunks to return.",
    )


def _minimum_similarity() -> float:
    try:
        value = float(os.getenv("AGENT_KNOWLEDGE_MIN_SIMILARITY", "0.25"))
    except ValueError:
        return 0.25
    return value if -1.0 <= value <= 1.0 else 0.25


def _search_chunks(
    query_vector: list[float],
    top_k: int,
    minimum_similarity: float,
) -> list[dict[str, Any]]:
    vector = Vector(query_vector)
    with connect_readonly() as connection:
        with connection.cursor() as guard_cursor:
            set_readonly_guards(guard_cursor)
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    c.chunk_id,
                    c.source_id,
                    c.chunk_index,
                    c.content,
                    c.metadata,
                    f.file_id,
                    f.original_filename,
                    1 - (c.embedding <=> %s) AS similarity
                FROM unstructured_knowledge_chunks c
                JOIN knowledge_files f ON f.file_id::text = c.source_id
                WHERE c.source_type = 'other'
                  AND vector_dims(c.embedding) = %s
                  AND LOWER(f.original_filename) NOT IN (
                      'rag_test_questions.csv',
                      'upload_manifest.csv',
                      'generation_assumptions.txt',
                      'cross_document_consistency_report.txt'
                  )
                  AND 1 - (c.embedding <=> %s) >= %s
                ORDER BY c.embedding <=> %s
                LIMIT %s
                """,
                (
                    vector,
                    len(query_vector),
                    vector,
                    minimum_similarity,
                    vector,
                    top_k,
                ),
            )
            rows = cursor.fetchall()

    return [
        {
            "chunk_id": row[0],
            "source_id": row[1],
            "chunk_index": row[2],
            "content": row[3],
            "metadata": row[4],
            "file_id": row[5],
            "filename": row[6],
            "similarity": round(float(row[7]), 6),
            "citation": f"[{row[6]}#{row[2]}]",
        }
        for row in rows
    ]


@tool(args_schema=KnowledgeSearchInput)
async def search_knowledge(query: str, top_k: int = 5) -> str:
    """Search uploaded business rules and return chunks with resolvable file citations."""

    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name="search_knowledge",
        top_k=top_k,
        query_length=len(query),
    )
    try:
        query_vector = await embedding_model.aembed_query(query)
        minimum_similarity = _minimum_similarity()
        matches = await asyncio.to_thread(
            _search_chunks,
            query_vector,
            top_k,
            minimum_similarity,
        )
    except Exception as error:
        logger.exception(
            "tool.failed",
            error,
            component="tool",
            tool_name="search_knowledge",
        )
        return json.dumps(
            {
                "success": False,
                "tool": "search_knowledge",
                "error_type": "retrieval_error",
                "error": "Uploaded knowledge evidence is temporarily unavailable.",
                "query": query,
                "matches": [],
                "sources": [],
            },
            ensure_ascii=False,
        )

    sources: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for match in matches:
        identity = (int(match["file_id"]), int(match["chunk_index"]))
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(
            {
                "file_id": match["file_id"],
                "filename": match["filename"],
                "chunk_index": match["chunk_index"],
                "citation": match["citation"],
                "similarity": match["similarity"],
                "download_url": f"/api/knowledge/files/{match['file_id']}/download",
            }
        )

    logger.tool_event(
        status="completed",
        tool_name="search_knowledge",
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        top_k=top_k,
        match_count=len(matches),
        minimum_similarity=minimum_similarity,
    )
    return json.dumps(
        {
            "success": True,
            "tool": "search_knowledge",
            "query": query,
            "minimum_similarity": minimum_similarity,
            "matches": matches,
            "sources": sources,
        },
        ensure_ascii=False,
        default=str,
    )


__all__ = ["KnowledgeSearchInput", "search_knowledge"]
