"""Streaming and compatibility endpoints for the business supervisor."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from pydantic import BaseModel, Field

from observability import logger
from rag.agent import run_supervisor, stream_supervisor
from rag.history_management import (
    ConversationMessage,
    SessionNotFoundError,
    session_manager,
)


router = APIRouter(prefix="/api", tags=["assistant"])


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


def _session_context(session_id: str, message: str) -> list[AnyMessage]:
    """Store the current user turn once and return bounded Agent context."""

    try:
        session_manager.add_message(session_id, "user", message)
        context = session_manager.get_context(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return [_to_agent_message(item) for item in context]


def _to_agent_message(message: ConversationMessage) -> AnyMessage:
    if message["role"] == "user":
        return HumanMessage(content=message["content"])
    return AIMessage(content=message["content"])


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """Stream safe progress, tool calls, answer tokens, and citations as SSE."""

    context = _session_context(request.session_id, request.message)

    async def events() -> AsyncIterator[str]:
        yield "retry: 3000\n\n"
        async for event in stream_supervisor(
            request.message,
            conversation_messages=context,
        ):
            if event["event"] == "done":
                answer = str(event["data"].get("answer") or "").strip()
                if answer:
                    try:
                        session_manager.add_message(
                            request.session_id,
                            "assistant",
                            answer,
                        )
                    except SessionNotFoundError:
                        # The user may delete the session while a stream is active.
                        pass
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

    context = _session_context(request.session_id, request.message)
    try:
        result = await run_supervisor(
            request.message,
            conversation_messages=context,
        )
    except Exception as exc:
        logger.exception("chat.request_failed", exc, component="chat")
        raise HTTPException(
            status_code=502,
            detail="The business supervisor could not complete this request",
        ) from exc
    answer = str(result.get("answer") or "").strip()
    if answer:
        try:
            session_manager.add_message(request.session_id, "assistant", answer)
        except SessionNotFoundError:
            pass
    return {"status": "completed", **result}
