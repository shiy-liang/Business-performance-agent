"""Load and validate RAG file-management settings from ``config/rag.yml``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "rag.yml"


class RagConfigError(ValueError):
    """Raised when the RAG configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class FileUploadConfig:
    storage_directory: Path
    max_file_size_bytes: int
    stream_chunk_size_bytes: int
    max_filename_length: int
    allow_unknown_mime_type: bool
    allowed_file_types: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class DocumentProcessingConfig:
    chunk_size: int
    chunk_overlap: int
    separators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RagConfig:
    file_upload: FileUploadConfig
    document_processing: DocumentProcessingConfig


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RagConfigError(f"{name} must be a mapping in {DEFAULT_CONFIG_PATH}")
    return value


def _positive_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RagConfigError(f"{name} must be a positive integer")
    return value


def _non_negative_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RagConfigError(f"{name} must be a non-negative integer")
    return value


def _allowed_file_types(value: Any) -> dict[str, frozenset[str]]:
    raw_types = _mapping(value, "file_upload.allowed_file_types")
    if not raw_types:
        raise RagConfigError("file_upload.allowed_file_types cannot be empty")

    result: dict[str, frozenset[str]] = {}
    for raw_extension, raw_mime_types in raw_types.items():
        if not isinstance(raw_extension, str) or not raw_extension.startswith("."):
            raise RagConfigError(
                "Each allowed file extension must be a string beginning with '.'"
            )
        if not isinstance(raw_mime_types, list) or not raw_mime_types:
            raise RagConfigError(
                f"MIME types for {raw_extension} must be a non-empty list"
            )
        if any(
            not isinstance(mime_type, str) or not mime_type.strip()
            for mime_type in raw_mime_types
        ):
            raise RagConfigError(
                f"Every MIME type for {raw_extension} must be a non-empty string"
            )
        extension = raw_extension.strip().lower()
        result[extension] = frozenset(
            mime_type.strip().lower() for mime_type in raw_mime_types
        )
    return result


@lru_cache(maxsize=1)
def load_rag_config(path: Path = DEFAULT_CONFIG_PATH) -> RagConfig:
    """Read and validate the RAG configuration once per process."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RagConfigError(f"RAG config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise RagConfigError(f"Invalid RAG YAML in {path}: {exc}") from exc

    root = _mapping(raw, "RAG config")
    upload = _mapping(root.get("file_upload"), "file_upload")
    processing = _mapping(root.get("document_processing"), "document_processing")
    raw_storage_directory = upload.get("storage_directory")
    if not isinstance(raw_storage_directory, str) or not raw_storage_directory.strip():
        raise RagConfigError("file_upload.storage_directory must be a non-empty string")

    storage_directory = Path(raw_storage_directory.strip())
    if not storage_directory.is_absolute():
        storage_directory = PROJECT_ROOT / storage_directory
    allow_unknown_mime_type = upload.get("allow_unknown_mime_type")
    if not isinstance(allow_unknown_mime_type, bool):
        raise RagConfigError("file_upload.allow_unknown_mime_type must be a boolean")

    chunk_size = _positive_integer(
        processing.get("chunk_size"), "document_processing.chunk_size"
    )
    chunk_overlap = _non_negative_integer(
        processing.get("chunk_overlap"), "document_processing.chunk_overlap"
    )
    if chunk_overlap >= chunk_size:
        raise RagConfigError(
            "document_processing.chunk_overlap must be smaller than chunk_size"
        )
    raw_separators = processing.get("separators")
    if not isinstance(raw_separators, list) or not raw_separators:
        raise RagConfigError("document_processing.separators must be a non-empty list")
    if any(not isinstance(separator, str) for separator in raw_separators):
        raise RagConfigError("Every document separator must be a string")

    return RagConfig(
        file_upload=FileUploadConfig(
            storage_directory=storage_directory.resolve(),
            max_file_size_bytes=_positive_integer(
                upload.get("max_file_size_bytes"),
                "file_upload.max_file_size_bytes",
            ),
            stream_chunk_size_bytes=_positive_integer(
                upload.get("stream_chunk_size_bytes"),
                "file_upload.stream_chunk_size_bytes",
            ),
            max_filename_length=_positive_integer(
                upload.get("max_filename_length"),
                "file_upload.max_filename_length",
            ),
            allow_unknown_mime_type=allow_unknown_mime_type,
            allowed_file_types=_allowed_file_types(upload.get("allowed_file_types")),
        ),
        document_processing=DocumentProcessingConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=tuple(raw_separators),
        ),
    )
