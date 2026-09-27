"""One shared, structured logger for the whole application.

Callers should import the module-level ``logger`` instance instead of creating
their own handlers.  The logger deliberately records operational metadata, not
model chain-of-thought, raw prompts, secrets, or database connection strings.
"""

from __future__ import annotations

import json
import logging
import re
import time as time_module
import traceback
from contextvars import ContextVar, Token
from datetime import datetime, time, timedelta
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Mapping

from config.logging import logging_settings

_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


class _WindowsSafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Keep logging when another Windows process temporarily owns the log file."""

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except PermissionError:
            # A concurrently running development server can hold the file open.
            # Defer rotation instead of dropping the current log record.
            self.rolloverAt = self.computeRollover(int(time_module.time()))


class LogManager:
    """Configure and expose the application's single logging pipeline."""

    _sensitive_keys = {
        "access_token",
        "api_key",
        "authorization",
        "auth_token",
        "connection_string",
        "cookie",
        "database_url",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
    _secret_patterns = (
        (re.compile(r"(?i)(bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
        (
            re.compile(r"(?i)(postgres(?:ql)?://[^:\s]+:)[^@\s]+(@)"),
            r"\1[REDACTED]\2",
        ),
    )

    def __init__(self) -> None:
        self._logger = logging.getLogger("business_performance")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._configure_once()

    def _configure_once(self) -> None:
        if any(
            getattr(handler, "_business_performance_handler", False)
            for handler in self._logger.handlers
        ):
            return

        log_directory = logging_settings.directory
        log_directory.mkdir(parents=True, exist_ok=True)

        formatter = logging.Formatter("%(message)s")

        console_handler = logging.StreamHandler()
        console_handler.setLevel(self._parse_level(logging_settings.console_level))
        console_handler.setFormatter(formatter)
        console_handler._business_performance_handler = True  # type: ignore[attr-defined]

        rotation_time_utc = self._rotation_time_utc()
        file_handler = _WindowsSafeTimedRotatingFileHandler(
            log_directory / "business-performance.log",
            when="midnight",
            interval=1,
            backupCount=logging_settings.backup_count,
            encoding="utf-8",
            utc=logging_settings.rotate_utc,
            atTime=rotation_time_utc,
        )
        file_handler.setLevel(self._parse_level(logging_settings.file_level))
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y%m%d"
        if self._timezone_offset().total_seconds() > 0:
            file_handler.namer = self._adjust_backup_date
        file_handler._business_performance_handler = True  # type: ignore[attr-defined]

        self._logger.addHandler(console_handler)
        self._logger.addHandler(file_handler)

    @staticmethod
    def _timezone_offset() -> timedelta:
        offset = datetime.now(logging_settings.timezone).utcoffset()
        return offset or timedelta(0)

    def _rotation_time_utc(self) -> time:
        """Return the UTC time that corresponds to midnight in the log timezone."""

        seconds = int((-self._timezone_offset().total_seconds()) % (24 * 60 * 60))
        hour, remainder = divmod(seconds, 60 * 60)
        minute, second = divmod(remainder, 60)
        return time(hour=hour, minute=minute, second=second)

    @staticmethod
    def _adjust_backup_date(default_name: str) -> str:
        """Label a positive-offset timezone's backup with its local business date."""

        prefix, separator, date_text = default_name.rpartition(".")
        if not separator:
            return default_name
        try:
            local_date = datetime.strptime(date_text, "%Y%m%d") + timedelta(days=1)
        except ValueError:
            return default_name
        return f"{prefix}.{local_date:%Y%m%d}"

    @staticmethod
    def _parse_level(value: str) -> int:
        level = getattr(logging, value, None)
        if not isinstance(level, int):
            raise ValueError(f"Unsupported log level: {value}")
        return level

    def bind_context(self, **fields: Any) -> Token[dict[str, Any]]:
        """Bind request/run identifiers to logs in the current async context."""

        context = {**_log_context.get(), **fields}
        return _log_context.set(self._sanitize_mapping(context))

    @staticmethod
    def reset_context(token: Token[dict[str, Any]]) -> None:
        """Restore the context that existed before ``bind_context``."""

        try:
            _log_context.reset(token)
        except ValueError:
            # Async generators can be finalized in a copied context when their
            # consumer stops early. Clear that copied context safely.
            _log_context.set({})

    def debug(self, event: str, message: str = "", **fields: Any) -> None:
        self._write(logging.DEBUG, event, message, fields)

    def info(self, event: str, message: str = "", **fields: Any) -> None:
        self._write(logging.INFO, event, message, fields)

    def warning(self, event: str, message: str = "", **fields: Any) -> None:
        self._write(logging.WARNING, event, message, fields)

    def error(self, event: str, message: str = "", **fields: Any) -> None:
        self._write(logging.ERROR, event, message, fields)

    def exception(
        self,
        event: str,
        error: BaseException,
        message: str = "",
        **fields: Any,
    ) -> None:
        """Record a sanitized exception and traceback as one JSON log entry."""

        fields = {
            **fields,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }
        self._write(logging.ERROR, event, message, fields)

    def model_event(
        self,
        *,
        status: str,
        model: str,
        duration_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        **fields: Any,
    ) -> None:
        """Record a model lifecycle event without logging prompts or reasoning."""

        write = self.error if status == "failed" else self.info
        write(
            f"model.{status}",
            component="model",
            model=model,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            **fields,
        )

    def tool_event(
        self,
        *,
        status: str,
        tool_name: str,
        duration_ms: float | None = None,
        **fields: Any,
    ) -> None:
        """Record a tool lifecycle event using summaries instead of raw payloads."""

        self.info(
            f"tool.{status}",
            component="tool",
            tool_name=tool_name,
            duration_ms=duration_ms,
            **fields,
        )

    def _write(
        self,
        level: int,
        event: str,
        message: str,
        fields: Mapping[str, Any],
    ) -> None:
        payload = {
            "timestamp": datetime.now(logging_settings.timezone).isoformat(),
            "level": logging.getLevelName(level).lower(),
            "service": "business-performance-agent",
            "environment": logging_settings.environment,
            "event": event,
            "message": message,
            **_log_context.get(),
            **fields,
        }
        sanitized = self._sanitize_mapping(payload)
        self._logger.log(level, json.dumps(sanitized, ensure_ascii=False, default=str))

    def _sanitize_mapping(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return {key: self._sanitize_value(key, item) for key, item in value.items()}

    def _sanitize_value(self, key: str, value: Any) -> Any:
        normalized_key = key.lower()
        is_sensitive_key = normalized_key in self._sensitive_keys or normalized_key.endswith(
            ("_password", "_secret", "_api_key", "_token")
        )
        if is_sensitive_key:
            return "[REDACTED]"
        if isinstance(value, Mapping):
            return self._sanitize_mapping(value)
        if isinstance(value, (list, tuple, set)):
            return [self._sanitize_value(key, item) for item in value]
        if isinstance(value, str):
            for pattern, replacement in self._secret_patterns:
                value = pattern.sub(replacement, value)
        return value


# The only LogManager instance used by the project.
logger = LogManager()
