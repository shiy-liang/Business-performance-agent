"""Shared PostgreSQL connection helpers."""

from __future__ import annotations

import psycopg

from config.settings import load_application_settings, load_environment_settings


def connect() -> psycopg.Connection:
    """Open a short-lived connection to the configured Supabase database."""

    database_url = load_environment_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    timeout = load_application_settings().database.connect_timeout_seconds
    return psycopg.connect(
        database_url,
        connect_timeout=timeout,
        prepare_threshold=None,
    )
