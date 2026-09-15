"""FastAPI middleware registration."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from observability.logging import logger


def register_logging_middleware(app: FastAPI) -> None:
    """Register request correlation, timing, and exception logging."""

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        started_at = perf_counter()
        context_token = logger.bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        logger.info("http.request.started", component="api")
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception(
                "http.request.failed",
                exc,
                component="api",
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            raise
        else:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "http.request.completed",
                component="api",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            logger.reset_context(context_token)

