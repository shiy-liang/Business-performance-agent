"""Run the supervisor and expose a stream suitable for the HTTP layer."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any, AsyncIterator
from uuid import uuid4

from langchain_core.messages import AnyMessage, HumanMessage

from model.config import load_model_config
from observability import logger
from rag.agent.bootstrap import initialize_agent_runtime
from rag.agent.graph import build_supervisor_graph
from rag.agent.middleware import AgentLoggingCallback, PublicEventMiddleware
from rag.agent.run_store import RunRecorder
from rag.agent.sql_approval import (
    SqlApprovalAlreadyDecidedError,
    SqlApprovalNotFoundError,
    sql_approval_manager,
)
from rag.agent.state import PublicAgentEvent
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


async def stream_supervisor(
    question: str,
    *,
    conversation_messages: list[AnyMessage] | None = None,
    graph: Any | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AsyncIterator[PublicAgentEvent]:
    """Yield safe progress, tool, citation, and answer-token events."""

    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question must not be empty")

    messages = (
        list(conversation_messages)
        if conversation_messages is not None
        else [HumanMessage(content=clean_question)]
    )
    run_id = str(uuid4())
    started_at = perf_counter()
    if graph is None and tool_registry is None:
        runtime = initialize_agent_runtime()
        registry = runtime.tool_registry
        active_graph = runtime.supervisor_graph
    else:
        registry = tool_registry or default_tool_registry
        active_graph = graph or build_supervisor_graph(tool_registry=registry)
    middleware = PublicEventMiddleware(registry.all_tool_names())
    recorder = RunRecorder(run_id)
    context_token = logger.bind_context(run_id=run_id, agent_name="supervisor")
    logger.info("agent.started", component="agent")
    try:
        await recorder.start(clean_question)
        started_event = middleware.started(run_id)
        await recorder.record(started_event)
        yield started_event

        chat_settings = load_model_config().chat_model
        reasoning_profiles = chat_settings.agent_reasoning_effort
        profile_summary = ", ".join(
            f"{name}={effort}" for name, effort in sorted(reasoning_profiles.items())
        )
        reasoning_event: PublicAgentEvent = {
            "event": "reasoning",
            "data": {
                "active": any(
                    effort != "none" for effort in reasoning_profiles.values()
                ),
                "effort": "adaptive",
                "profiles": reasoning_profiles,
                "message": f"Qwen reasoning is allocated by Agent phase: {profile_summary}.",
            },
        }
        await recorder.record(reasoning_event)
        yield reasoning_event

        skills_event: PublicAgentEvent = {
            "event": "skills",
            "data": {
                "items": ["Business Diagnosis", "Evidence Policy"],
                "message": "Business Diagnosis and Evidence Policy skills were applied.",
            },
        }
        await recorder.record(skills_event)
        yield skills_event

        async for raw_event in active_graph.astream_events(
            {
                "run_id": run_id,
                "user_question": clean_question,
                "messages": messages,
            },
            config={
                "recursion_limit": 10,
                "run_name": "business-supervisor",
                "callbacks": [AgentLoggingCallback()],
                "configurable": {
                    "run_id": run_id,
                    "delegation_runtime_state": {},
                },
            },
            version="v2",
        ):
            for public_event in middleware.translate(raw_event):
                await recorder.record(public_event)
                yield public_event
    except (asyncio.CancelledError, GeneratorExit):
        await recorder.fail("stream_cancelled")
        raise
    except Exception as error:
        logger.exception("agent.failed", error, component="agent")
        await recorder.fail("agent_execution_failed")
        error_event: PublicAgentEvent = {
            "event": "error",
            "data": {
                "run_id": run_id,
                "message": "The supervisor could not complete this request.",
            },
        }
        yield error_event
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
    await recorder.complete(
        duration_ms=duration_ms,
        evidence_count=len(middleware.sources),
    )
    done_event: PublicAgentEvent = {
        "event": "done",
        "data": {
            "run_id": run_id,
            "answer": middleware.answer,
            "sources": middleware.sources,
            "duration_ms": duration_ms,
        },
    }
    yield done_event


async def run_supervisor(question: str, **kwargs: Any) -> dict[str, Any]:
    """Collect the streaming supervisor response for non-streaming clients."""

    final: dict[str, Any] = {}
    async for event in stream_supervisor(question, **kwargs):
        if event["event"] == "sql_approval":
            # A collected (non-streaming) client cannot display an interactive
            # approval while the request is open. Fail closed instead of running
            # model-generated SQL without explicit consent.
            approval_id = str(event["data"].get("approval_id") or "")
            try:
                await sql_approval_manager.decide(approval_id, "cancel")
            except (SqlApprovalNotFoundError, SqlApprovalAlreadyDecidedError):
                pass
        elif event["event"] == "done":
            final = event["data"]
        elif event["event"] == "error":
            raise RuntimeError(str(event["data"].get("message")))
    return final


__all__ = ["run_supervisor", "stream_supervisor"]
