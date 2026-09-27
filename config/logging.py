"""Typed configuration for the shared application logger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import load_environment_settings


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """Validated logging settings loaded once when the process starts."""

    environment: str
    directory: Path
    console_level: str
    file_level: str
    backup_count: int
    rotate_utc: bool
    timezone: ZoneInfo

    @classmethod
    def from_env(cls) -> "LoggingSettings":
        environment = load_environment_settings()
        return cls(
            environment=environment.app_env,
            directory=Path(environment.log_directory),
            console_level=environment.log_console_level,
            file_level=environment.log_file_level,
            backup_count=environment.log_backup_count,
            rotate_utc=environment.log_rotate_utc,
            timezone=environment.log_timezone,
        )


logging_settings = LoggingSettings.from_env()
