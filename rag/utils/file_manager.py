"""Validate, hash, and persist uploaded knowledge-base files.

This module deliberately stops before text extraction, chunking, embedding, or
pgvector writes.  It owns only the source-file lifecycle and its validation.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from rag.utils.config import FileUploadConfig, load_rag_config

class FileValidationError(ValueError):
    """Raised when an uploaded file does not meet the ingestion policy."""


@dataclass(frozen=True, slots=True)
class StagedKnowledgeFile:
    """A validated upload held temporarily before its database transaction."""

    original_filename: str
    file_hash: str
    mime_type: str | None
    file_size: int
    extension: str
    temporary_path: Path

    @property
    def storage_path(self) -> str:
        """Return a stable, repository-independent path for database storage."""

        return f"{self.file_hash[:2]}/{self.file_hash}"


def format_allowed_extensions(config: FileUploadConfig | None = None) -> str:
    settings = config or load_rag_config().file_upload
    return ", ".join(sorted(settings.allowed_file_types))


def _safe_original_filename(filename: str | None, max_length: int) -> str:
    if not filename or not filename.strip():
        raise FileValidationError("The filename cannot be empty")

    # Browsers normally send only a basename. Normalising both separators also
    # protects the storage layer from crafted Windows/POSIX traversal names.
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if basename in {"", ".", ".."} or "\x00" in basename:
        raise FileValidationError("The filename is invalid")
    if len(basename) > max_length:
        raise FileValidationError(
            f"The filename cannot exceed {max_length} characters"
        )
    return basename


def _normalise_mime_type(mime_type: str | None) -> str | None:
    if not mime_type:
        return None
    return mime_type.split(";", 1)[0].strip().lower() or None


def _validate_file_type(
    filename: str,
    mime_type: str | None,
    config: FileUploadConfig,
) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in config.allowed_file_types:
        raise FileValidationError(
            f"Unsupported {extension or 'extensionless'} file; allowed types: "
            f"{format_allowed_extensions(config)}"
        )

    # Some browsers/operating systems cannot determine a MIME type and send an
    # empty value or application/octet-stream. The content signature check below
    # remains authoritative for PDF and rejects obvious binary TXT/CSV uploads.
    unknown_mime_types = {None, "application/octet-stream"}
    if not (config.allow_unknown_mime_type and mime_type in unknown_mime_types):
        allowed_mime_types = config.allowed_file_types[extension]
        if mime_type not in allowed_mime_types:
            raise FileValidationError(
                f"File extension {extension} does not match MIME type {mime_type}"
            )
    return extension


def _validate_content(extension: str, leading_bytes: bytes, saw_null_byte: bool) -> None:
    if extension == ".pdf" and not leading_bytes.startswith(b"%PDF-"):
        raise FileValidationError("The PDF file signature is invalid")
    if extension in {".txt", ".csv"} and saw_null_byte:
        raise FileValidationError("TXT and CSV files cannot contain binary null bytes")


def stage_and_hash_file(
    source: BinaryIO,
    *,
    original_filename: str | None,
    mime_type: str | None,
    upload_directory: Path | None = None,
    max_file_size: int | None = None,
    stream_chunk_size: int | None = None,
) -> StagedKnowledgeFile:
    """Stream an upload to a temporary file while calculating SHA-256."""

    config = load_rag_config().file_upload
    active_upload_directory = upload_directory or config.storage_directory
    active_max_file_size = (
        config.max_file_size_bytes if max_file_size is None else max_file_size
    )
    active_stream_chunk_size = (
        config.stream_chunk_size_bytes
        if stream_chunk_size is None
        else stream_chunk_size
    )
    filename = _safe_original_filename(original_filename, config.max_filename_length)
    normalised_mime = _normalise_mime_type(mime_type)
    extension = _validate_file_type(filename, normalised_mime, config)
    if active_max_file_size <= 0:
        raise ValueError("max_file_size must be positive")
    if active_stream_chunk_size <= 0:
        raise ValueError("stream_chunk_size must be positive")

    temporary_directory = active_upload_directory.resolve() / ".staging"
    temporary_directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="upload-", suffix=".tmp", dir=temporary_directory
    )
    temporary_path = Path(temporary_name)
    digest = hashlib.sha256()
    file_size = 0
    leading_bytes = b""
    saw_null_byte = False

    try:
        with os.fdopen(descriptor, "wb") as destination:
            while chunk := source.read(active_stream_chunk_size):
                if not isinstance(chunk, bytes):
                    raise FileValidationError("Uploaded content must be binary")
                file_size += len(chunk)
                if file_size > active_max_file_size:
                    raise FileValidationError(
                        f"File exceeds the {active_max_file_size // (1024 * 1024)} MB size limit"
                    )
                if len(leading_bytes) < 8:
                    leading_bytes += chunk[: 8 - len(leading_bytes)]
                saw_null_byte = saw_null_byte or b"\x00" in chunk
                digest.update(chunk)
                destination.write(chunk)

        if file_size == 0:
            raise FileValidationError("Empty files cannot be uploaded")
        _validate_content(extension, leading_bytes, saw_null_byte)
        return StagedKnowledgeFile(
            original_filename=filename,
            file_hash=digest.hexdigest(),
            mime_type=normalised_mime,
            file_size=file_size,
            extension=extension,
            temporary_path=temporary_path,
        )
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def resolve_storage_path(
    storage_path: str,
    *,
    upload_directory: Path | None = None,
) -> Path:
    """Resolve a database path and guarantee it remains inside managed storage."""

    root = (upload_directory or load_rag_config().file_upload.storage_directory).resolve()
    candidate = (root / storage_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FileValidationError(
            "The database file path is outside the knowledge storage directory"
        ) from exc
    if candidate == root:
        raise FileValidationError("The database file path is invalid")
    return candidate


def persist_staged_file(
    staged: StagedKnowledgeFile,
    *,
    upload_directory: Path | None = None,
) -> tuple[Path, bool]:
    """Atomically move a staged file into hash-addressed managed storage."""

    destination = resolve_storage_path(
        staged.storage_path, upload_directory=upload_directory
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    already_existed = destination.exists()
    os.replace(staged.temporary_path, destination)
    return destination, not already_existed


def delete_managed_file(
    storage_path: str,
    *,
    upload_directory: Path | None = None,
) -> bool:
    """Delete one managed file and prune its empty hash-prefix directory."""

    path = resolve_storage_path(storage_path, upload_directory=upload_directory)
    if not path.exists():
        return False
    if not path.is_file():
        raise FileValidationError("The knowledge storage path is not a regular file")
    path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass
    return True
