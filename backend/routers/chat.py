"""Streaming and compatibility endpoints for the business supervisor."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from observability import logger
from rag.agent import run_supervisor, stream_supervisor


router = APIRouter(prefix="/api", tags=["assistant"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """Stream safe progress, tool calls, answer tokens, and citations as SSE."""

    async def events() -> AsyncIterator[str]:
        yield "retry: 3000\n\n"
        async for event in stream_supervisor(request.message):
            yield _sse(event["event"], event["data"])

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat(request: ChatRequest) -> dict[str, object]:
    """Return the collected supervisor result for non-streaming clients."""

    try:
        result = await run_supervisor(request.message)
    except Exception as exc:
        logger.exception("chat.request_failed", exc, component="chat")
        raise HTTPException(
            status_code=502,
            detail="The business supervisor could not complete this request",
        ) from exc
    return {"status": "completed", **result}
