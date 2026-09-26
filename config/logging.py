"""Typed configuration for the shared application logger."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _read_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc

    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """Validated logging settings loaded once when the process starts."""

    environment: str
    directory: Path
    console_level: str
    file_level: str
    backup_count: int
    timezone: ZoneInfo

    @classmethod
    def from_env(cls) -> "LoggingSettings":
        directory = Path(os.getenv("LOG_DIRECTORY", "logs"))
        if not directory.is_absolute():
            directory = PROJECT_ROOT / directory

        timezone_name = os.getenv("LOG_TIMEZONE", "Asia/Singapore")
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unsupported LOG_TIMEZONE: {timezone_name}") from exc

        return cls(
            environment=os.getenv("APP_ENV", "development"),
            directory=directory,
            console_level=os.getenv("LOG_CONSOLE_LEVEL", "INFO").upper(),
            file_level=os.getenv("LOG_FILE_LEVEL", "DEBUG").upper(),
            backup_count=_read_int("LOG_BACKUP_COUNT", 14, minimum=1),
            timezone=timezone,
        )


logging_settings = LoggingSettings.from_env()
