"""Run the supervisor and expose a stream suitable for the HTTP layer."""

from __future__ import annotations

from time import perf_counter
from typing import Any, AsyncIterator
from uuid import uuid4

from langchain_core.messages import HumanMessage

from model.config import load_model_config
from observability import logger
from rag.agent.graph import build_supervisor_graph
from rag.agent.middleware import AgentLoggingCallback, PublicEventMiddleware
from rag.agent.state import PublicAgentEvent
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


async def stream_supervisor(
    question: str,
    *,
    graph: Any | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AsyncIterator[PublicAgentEvent]:
    """Yield safe progress, tool, citation, and answer-token events."""

    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question must not be empty")

    run_id = str(uuid4())
    started_at = perf_counter()
    registry = tool_registry or default_tool_registry
    active_graph = graph or build_supervisor_graph(tool_registry=registry)
    middleware = PublicEventMiddleware(registry.all_tool_names())
    context_token = logger.bind_context(run_id=run_id, agent_name="supervisor")
    logger.info("agent.started", component="agent")
    yield middleware.started(run_id)
    chat_settings = load_model_config().chat_model
    yield {
        "event": "reasoning",
        "data": {
            "active": chat_settings.reasoning_effort != "none",
            "effort": chat_settings.reasoning_effort,
            "message": (
                f"Qwen reasoning is enabled at {chat_settings.reasoning_effort} effort."
                if chat_settings.reasoning_effort != "none"
                else "Qwen reasoning is disabled for this request."
            ),
        },
    }
    yield {
        "event": "skills",
        "data": {
            "items": ["Business Diagnosis", "Evidence Policy"],
            "message": "Business Diagnosis and Evidence Policy skills were applied.",
        },
    }

    try:
        async for raw_event in active_graph.astream_events(
            {
                "run_id": run_id,
                "user_question": clean_question,
                "messages": [HumanMessage(content=clean_question)],
            },
            config={
                "recursion_limit": 10,
                "run_name": "business-supervisor",
                "callbacks": [AgentLoggingCallback()],
            },
            version="v2",
        ):
            for public_event in middleware.translate(raw_event):
                yield public_event
    except Exception as error:
        logger.exception("agent.failed", error, component="agent")
        yield {
            "event": "error",
            "data": {
                "run_id": run_id,
                "message": "The supervisor could not complete this request.",
            },
        }
        return
    finally:
        logger.reset_context(context_token)

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "agent.completed",
        component="agent",
        agent_name="supervisor",
        run_id=run_id,
        duration_ms=duration_ms,
        evidence_count=len(middleware.sources),
    )
    yield {
        "event": "done",
        "data": {
            "run_id": run_id,
            "answer": middleware.answer,
            "sources": middleware.sources,
            "duration_ms": duration_ms,
        },
    }


async def run_supervisor(question: str, **kwargs: Any) -> dict[str, Any]:
    """Collect the streaming supervisor response for non-streaming clients."""

    final: dict[str, Any] = {}
    async for event in stream_supervisor(question, **kwargs):
        if event["event"] == "done":
            final = event["data"]
        elif event["event"] == "error":
            raise RuntimeError(str(event["data"].get("message")))
    return final


__all__ = ["run_supervisor", "stream_supervisor"]
