"""Translate LangChain callbacks into safe public progress events."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Iterable
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import LLMResult

from observability import logger
from rag.agent.state import PublicAgentEvent


def content_text(content: Any) -> str:
    """Extract answer text while deliberately ignoring private reasoning blocks."""

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", ""))
        if block_type not in {"text", "output_text"}:
            continue
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _contains_reasoning(content: Any) -> bool:
    """Detect reasoning metadata without returning private reasoning text."""

    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict)
        and str(block.get("type", "")) in {"reasoning", "reasoning_summary"}
        for block in content
    )


def _tool_payload(output: Any) -> dict[str, Any] | None:
    if isinstance(output, ToolMessage):
        output = output.content
    if isinstance(output, list) and len(output) == 1 and isinstance(output[0], ToolMessage):
        output = output[0].content
    if not isinstance(output, str):
        return None
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _final_message(output: Any) -> AIMessage | None:
    if not isinstance(output, dict):
        return None
    messages = output.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return message
    return None


class PublicEventMiddleware:
    """A middleware-style adapter for UI-safe progress, tools, and citations."""

    def __init__(self, allowed_tools: Iterable[str]) -> None:
        self.allowed_tools = frozenset(allowed_tools)
        self.answer_parts: list[str] = []
        self.sources: list[dict[str, Any]] = []
        self._streamed_text = False
        self._reasoning_announced = False
        self._announced_specialists: set[str] = set()

    def started(self, run_id: str) -> PublicAgentEvent:
        return {
            "event": "status",
            "data": {
                "run_id": run_id,
                "stage": "thinking",
                "message": "Understanding the question and selecting the right capability.",
            },
        }

    def translate(self, event: dict[str, Any]) -> list[PublicAgentEvent]:
        event_type = event.get("event")
        name = str(event.get("name", ""))
        data = event.get("data") or {}
        tags = set(event.get("tags") or [])
        translated: list[PublicAgentEvent] = []

        if (
            event_type == "on_chain_start"
            and name in {"finance-agent", "operations-agent"}
            and name not in self._announced_specialists
        ):
            self._announced_specialists.add(name)
            label = "Finance" if name == "finance-agent" else "Operations"
            translated.extend(
                [
                    {
                        "event": "status",
                        "data": {
                            "stage": "specialist",
                            "message": f"{label} Agent is analyzing structured business data.",
                        },
                    },
                    {
                        "event": "skills",
                        "data": {
                            "items": [f"{label} SQL Query", "SQL Safety"],
                            "message": f"{label} SQL Query and SQL Safety skills were applied.",
                        },
                    },
                ]
            )
        elif event_type == "on_tool_start" and name in self.allowed_tools:
            translated.extend(
                [
                    {
                        "event": "status",
                        "data": {
                            "stage": "tool",
                            "message": self._tool_start_message(name),
                        },
                    },
                    {
                        "event": "tool_start",
                        "data": {"name": name, "message": f"{name} was called."},
                    },
                ]
            )
        elif event_type == "on_tool_end" and name in self.allowed_tools:
            payload = _tool_payload(data.get("output"))
            if payload:
                sources = payload.get("sources")
                if isinstance(sources, list):
                    added: list[dict[str, Any]] = []
                    existing = {
                        str(item.get("citation") or item) for item in self.sources
                    }
                    for item in sources:
                        if not isinstance(item, dict):
                            continue
                        identity = str(item.get("citation") or item)
                        if identity in existing:
                            continue
                        existing.add(identity)
                        self.sources.append(item)
                        added.append(item)
                    if added:
                        translated.append(
                            {"event": "sources", "data": {"items": self.sources}}
                        )
            translated.extend(
                [
                    {
                        "event": "tool_end",
                        "data": {"name": name, "message": self._tool_end_message(name, payload)},
                    },
                    {
                        "event": "status",
                        "data": {
                            "stage": "answering",
                            "message": "Evidence is ready. Preparing the final answer.",
                        },
                    },
                ]
            )
        elif event_type == "on_chat_model_stream" and "public-answer" in tags:
            chunk = data.get("chunk")
            if isinstance(chunk, AIMessageChunk):
                if _contains_reasoning(chunk.content) and not self._reasoning_announced:
                    self._reasoning_announced = True
                    translated.append(
                        {
                            "event": "reasoning",
                            "data": {
                                "active": True,
                                "message": "The model is reasoning over the available context.",
                            },
                        }
                    )
                text = content_text(chunk.content)
                if text:
                    self._streamed_text = True
                    self.answer_parts.append(text)
                    translated.append({"event": "token", "data": {"text": text}})
        elif event_type == "on_chain_end" and name == "business-supervisor":
            if not self._streamed_text:
                message = _final_message(data.get("output"))
                if message is not None:
                    text = content_text(message.content)
                    if text:
                        self.answer_parts.append(text)
                        translated.append({"event": "token", "data": {"text": text}})

        return translated

    @property
    def answer(self) -> str:
        return "".join(self.answer_parts).strip()

    @staticmethod
    def _tool_start_message(name: str) -> str:
        messages = {
            "search_knowledge": "Searching the uploaded knowledge base for supporting rules.",
            "delegate_finance": "Preparing a structured task for the Finance Agent.",
            "delegate_operations": "Preparing a structured task for the Operations Agent.",
            "search_finance_schema": "Finance is selecting authorized tables and columns.",
            "resolve_finance_entity": "Finance is matching the requested entity to database values.",
            "execute_finance_sql": "Finance is validating and running a read-only SQL query.",
            "search_operations_schema": "Operations is selecting authorized tables and columns.",
            "resolve_operations_entity": "Operations is matching the requested entity to database values.",
            "execute_operations_sql": "Operations is validating and running a read-only SQL query.",
        }
        return messages.get(name, f"Running {name}.")

    @staticmethod
    def _tool_end_message(name: str, payload: dict[str, Any] | None) -> str:
        if name == "search_knowledge" and payload:
            count = len(payload.get("matches") or [])
            return f"{name} returned {count} relevant knowledge chunks."
        if name.startswith("search_") and name.endswith("_schema") and payload:
            return f"{name} returned {len(payload.get('tables') or [])} authorized schemas."
        if name.startswith("resolve_") and name.endswith("_entity") and payload:
            return f"{name} returned {len(payload.get('candidates') or [])} candidates."
        if name.startswith("execute_") and name.endswith("_sql") and payload:
            if payload.get("success"):
                return f"{name} returned {payload.get('row_count', 0)} rows."
            return f"{name} reported {payload.get('error_type', 'an error')}; the specialist may revise the query."
        return f"{name} completed."


class AgentLoggingCallback(AsyncCallbackHandler):
    """Record model lifecycle metadata without prompts or private reasoning."""

    def __init__(self) -> None:
        self._started_at: dict[UUID, float] = {}
        self._models: dict[UUID, str] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        invocation = kwargs.get("invocation_params") or {}
        model = str(
            invocation.get("model")
            or invocation.get("model_name")
            or serialized.get("name")
            or "unknown"
        )
        self._started_at[run_id] = perf_counter()
        self._models[run_id] = model
        logger.model_event(status="started", model=model, operation="responses")

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at = self._started_at.pop(run_id, perf_counter())
        model = self._models.pop(run_id, "unknown")
        usage = (response.llm_output or {}).get("token_usage") or {}
        logger.model_event(
            status="completed",
            model=model,
            operation="responses",
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
            output_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at = self._started_at.pop(run_id, perf_counter())
        model = self._models.pop(run_id, "unknown")
        logger.model_event(
            status="failed",
            model=model,
            operation="responses",
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            error_type=type(error).__name__,
        )


__all__ = ["AgentLoggingCallback", "PublicEventMiddleware", "content_text"]
