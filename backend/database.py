"""Shared PostgreSQL connection helpers."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


_pool: ConnectionPool | None = None


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def open_pool() -> None:
    """Open the process-wide pool used by all database requests."""

    global _pool
    if _pool is not None:
        return

    _pool = ConnectionPool(
        conninfo=_database_url(),
        min_size=max(1, int(os.getenv("DB_POOL_MIN_SIZE", "1"))),
        max_size=max(1, int(os.getenv("DB_POOL_MAX_SIZE", "5"))),
        timeout=5,
        kwargs={"connect_timeout": 5, "prepare_threshold": None},
        open=False,
    )
    _pool.open(wait=True)


def close_pool() -> None:
    """Close the process-wide pool during application shutdown."""

    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the shared pool for one operation."""

    open_pool()
    assert _pool is not None
    with _pool.connection() as connection:
        yield connection
