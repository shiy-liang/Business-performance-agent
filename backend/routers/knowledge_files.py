"""Knowledge-base source file upload and lifecycle endpoints."""

from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from starlette.concurrency import run_in_threadpool

from backend.database import connect
from observability import logger
from rag.utils import (
    FileValidationError,
    RagConfigError,
    delete_managed_file,
    format_allowed_extensions,
    load_rag_config,
    persist_staged_file,
    resolve_storage_path,
    stage_and_hash_file,
)
from rag.utils.vector_store import SOURCE_TYPE, ingest_knowledge_file


router = APIRouter(prefix="/api/knowledge/files", tags=["knowledge-files"])


def _file_response(row: dict[str, object]) -> dict[str, object]:
    created_at = row["created_at"]
    return {
        "file_id": row["file_id"],
        "original_filename": row["original_filename"],
        "file_hash": str(row["file_hash"]).strip(),
        "mime_type": row["mime_type"],
        "file_size": row["file_size"],
        "created_at": created_at.isoformat() if created_at else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_knowledge_file(file: UploadFile = File(...)) -> dict[str, object]:
    """Validate, save, embed, and register one knowledge source file."""

    try:
        staged = await run_in_threadpool(
            stage_and_hash_file,
            file.file,
            original_filename=file.filename,
            mime_type=file.content_type,
        )
    except FileValidationError as exc:
        logger.warning(
            "knowledge_file.validation_failed",
            message=str(exc),
            component="knowledge_files",
            original_filename=file.filename,
            mime_type=file.content_type,
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (OSError, RagConfigError) as exc:
        logger.exception(
            "knowledge_file.staging_failed",
            exc,
            component="knowledge_files",
            original_filename=file.filename,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The uploaded file could not be staged",
        ) from exc

    logger.info(
        "knowledge_file.validated",
        component="knowledge_files",
        original_filename=staged.original_filename,
        file_hash=staged.file_hash,
        mime_type=staged.mime_type,
        file_size=staged.file_size,
    )

    destination: Path | None = None
    destination_created = False
    try:
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    INSERT INTO knowledge_files (
                        original_filename, file_hash, storage_path, mime_type, file_size
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (file_hash) DO NOTHING
                    RETURNING file_id, original_filename, file_hash, storage_path,
                              mime_type, file_size, created_at
                    """,
                    (
                        staged.original_filename,
                        staged.file_hash,
                        staged.storage_path,
                        staged.mime_type,
                        staged.file_size,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """
                        SELECT file_id, original_filename, file_hash, storage_path,
                               mime_type, file_size, created_at
                        FROM knowledge_files
                        WHERE file_hash = %s
                        """,
                        (staged.file_hash,),
                    )
                    existing = cursor.fetchone()
                    logger.info(
                        "knowledge_file.duplicate_rejected",
                        component="knowledge_files",
                        original_filename=staged.original_filename,
                        file_hash=staged.file_hash,
                        existing_file_id=existing["file_id"] if existing else None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A file with identical content already exists",
                    )

                destination, destination_created = persist_staged_file(staged)
                ingestion = await ingest_knowledge_file(
                    connection,
                    file_id=int(row["file_id"]),
                    file_path=destination,
                    original_filename=staged.original_filename,
                    file_hash=staged.file_hash,
                    extension=staged.extension,
                )

        payload = _file_response(dict(row))
        logger.info(
            "knowledge_file.uploaded",
            component="knowledge_files",
            file_id=payload["file_id"],
            original_filename=payload["original_filename"],
            file_hash=payload["file_hash"],
            file_size=payload["file_size"],
        )
        return {
            "status": "created",
            "file": payload,
            "knowledge": {
                "source_type": ingestion.source_type,
                "source_id": ingestion.source_id,
                "chunk_count": ingestion.chunk_count,
                "embedding_dimensions": ingestion.embedding_dimensions,
                "embedding_model": ingestion.embedding_model,
            },
        }
    except HTTPException:
        raise
    except RuntimeError as exc:
        if destination_created and destination is not None:
            destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge file could not be processed",
        ) from exc
    except psycopg.Error as exc:
        if destination_created and destination is not None:
            destination.unlink(missing_ok=True)
        logger.exception(
            "knowledge_file.database_write_failed",
            exc,
            component="knowledge_files",
            original_filename=staged.original_filename,
            file_hash=staged.file_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge file database write failed",
        ) from exc
    except (OSError, FileValidationError) as exc:
        if destination_created and destination is not None:
            destination.unlink(missing_ok=True)
        logger.exception(
            "knowledge_file.storage_write_failed",
            exc,
            component="knowledge_files",
            original_filename=staged.original_filename,
            file_hash=staged.file_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The knowledge file could not be saved",
        ) from exc
    except Exception as exc:
        if destination_created and destination is not None:
            destination.unlink(missing_ok=True)
        logger.exception(
            "knowledge_file.processing_failed",
            exc,
            component="knowledge_files",
            original_filename=staged.original_filename,
            file_hash=staged.file_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The knowledge file could not be processed",
        ) from exc
    finally:
        staged.temporary_path.unlink(missing_ok=True)


@router.get("")
def list_knowledge_files() -> dict[str, object]:
    """List registered source files, newest first."""

    try:
        config = load_rag_config().file_upload
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT file_id, original_filename, file_hash, storage_path,
                           mime_type, file_size, created_at
                    FROM knowledge_files
                    ORDER BY created_at DESC, file_id DESC
                    """
                )
                rows = [_file_response(dict(row)) for row in cursor.fetchall()]
    except (RuntimeError, RagConfigError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception(
            "knowledge_file.list_failed",
            exc,
            component="knowledge_files",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge file list could not be loaded",
        ) from exc

    return {
        "files": rows,
        "count": len(rows),
        "upload_policy": {
            "allowed_extensions": format_allowed_extensions(config).split(", "),
            "max_file_size_bytes": config.max_file_size_bytes,
            "stream_chunk_size_bytes": config.stream_chunk_size_bytes,
            "max_filename_length": config.max_filename_length,
        },
    }


def _lookup_file(file_id: int) -> dict[str, object]:
    try:
        with connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT file_id, original_filename, file_hash, storage_path,
                           mime_type, file_size, created_at
                    FROM knowledge_files
                    WHERE file_id = %s
                    """,
                    (file_id,),
                )
                row = cursor.fetchone()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception(
            "knowledge_file.lookup_failed",
            exc,
            component="knowledge_files",
            file_id=file_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge file could not be loaded",
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The knowledge file does not exist",
        )
    return dict(row)


@router.get("/{file_id}/download")
def download_knowledge_file(file_id: int) -> FileResponse:
    """Download one managed source file using its original filename."""

    row = _lookup_file(file_id)
    try:
        path = resolve_storage_path(str(row["storage_path"]))
    except FileValidationError as exc:
        logger.exception(
            "knowledge_file.invalid_storage_path",
            exc,
            component="knowledge_files",
            file_id=file_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The knowledge file storage path is invalid",
        ) from exc
    if not path.is_file():
        logger.error(
            "knowledge_file.missing_from_storage",
            component="knowledge_files",
            file_id=file_id,
            storage_path=row["storage_path"],
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The knowledge source file is missing from storage",
        )

    return FileResponse(
        path,
        media_type=str(row["mime_type"] or "application/octet-stream"),
        filename=str(row["original_filename"]),
    )


@router.delete("/{file_id}")
def remove_knowledge_file(file_id: int) -> dict[str, object]:
    """Remove a knowledge file registration and its managed source file."""

    row = _lookup_file(file_id)
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM unstructured_knowledge_chunks
                    WHERE source_type = %s AND source_id = %s
                    """,
                    (SOURCE_TYPE, str(file_id)),
                )
                deleted_chunk_count = cursor.rowcount
                cursor.execute("DELETE FROM knowledge_files WHERE file_id = %s", (file_id,))
                if cursor.rowcount != 1:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="The knowledge file does not exist",
                    )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception(
            "knowledge_file.delete_database_failed",
            exc,
            component="knowledge_files",
            file_id=file_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge file record could not be deleted",
        ) from exc

    try:
        removed_from_storage = delete_managed_file(str(row["storage_path"]))
    except (OSError, FileValidationError) as exc:
        removed_from_storage = False
        logger.exception(
            "knowledge_file.delete_storage_failed",
            exc,
            component="knowledge_files",
            file_id=file_id,
            storage_path=row["storage_path"],
        )

    logger.info(
        "knowledge_file.deleted",
        component="knowledge_files",
        file_id=file_id,
        original_filename=row["original_filename"],
        file_hash=str(row["file_hash"]).strip(),
        deleted_chunk_count=deleted_chunk_count,
        removed_from_storage=removed_from_storage,
    )
    return {
        "status": "deleted",
        "file_id": file_id,
        "deleted_chunk_count": deleted_chunk_count,
        "removed_from_storage": removed_from_storage,
    }
