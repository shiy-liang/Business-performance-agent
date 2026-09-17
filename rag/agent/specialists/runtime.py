"""Run specialists and register them with the supervisor dispatcher."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from observability import logger
from rag.agent.middleware import content_text
from rag.agent.specialists.graph import SpecialistName, build_specialist_graph
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


def _collect_sources(messages: list[Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for message in messages:
        if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        for source in payload.get("sources") or []:
            if not isinstance(source, dict):
                continue
            identity = str(source.get("citation") or source)
            if identity not in seen:
                seen.add(identity)
                sources.append(source)
    return sources


def _final_answer(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return content_text(message.content).strip()
    return ""


async def run_specialist_agent(
    agent_name: SpecialistName,
    task: str,
    *,
    config: RunnableConfig | None = None,
    graph: Any | None = None,
    tool_registry: ToolRegistry | None = None,
) -> dict[str, object]:
    """Execute one specialist while preserving parent callbacks and run context."""

    started_at = perf_counter()
    registry = tool_registry or default_tool_registry
    active_graph = graph or build_specialist_graph(
        agent_name,
        tool_registry=registry,
    )
    child_config: RunnableConfig = dict(config or {})
    child_config["run_name"] = f"{agent_name}-agent"
    child_config["recursion_limit"] = 16
    child_config["tags"] = [agent_name, "specialist"]
    configurable = dict(child_config.get("configurable") or {})
    configurable.update(
        {
            "agent_name": agent_name,
            "sql_runtime_state": {"attempts": 0},
        }
    )
    child_config["configurable"] = configurable

    context_token = logger.bind_context(agent_name=agent_name)
    logger.info("agent.started", component="agent", specialist_task_length=len(task))
    try:
        result = await active_graph.ainvoke(
            {
                "task": task,
                "agent_name": agent_name,
                "messages": [HumanMessage(content=task)],
            },
            config=child_config,
        )
    except Exception as error:
        logger.exception("agent.failed", error, component="agent")
        raise
    finally:
        logger.reset_context(context_token)

    messages = list(result.get("messages") or [])
    answer = _final_answer(messages)
    sources = _collect_sources(messages)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "agent.completed",
        component="agent",
        agent_name=agent_name,
        duration_ms=duration_ms,
        evidence_count=len(sources),
    )
    return {
        "status": "completed" if answer else "incomplete",
        "agent": agent_name,
        "answer": answer,
        "sources": sources,
        "duration_ms": duration_ms,
    }


_DEFAULT_SPECIALISTS_REGISTERED = False


def ensure_default_specialists_registered() -> None:
    """Connect both specialist handlers once without changing supervisor tools."""

    global _DEFAULT_SPECIALISTS_REGISTERED
    if _DEFAULT_SPECIALISTS_REGISTERED:
        return
    from rag.agent.specialists.finance import run_finance_agent
    from rag.agent.specialists.operations import run_operations_agent
    from rag.agent.tools.supervisor.delegation import specialist_dispatcher

    specialist_dispatcher.register("finance", run_finance_agent)
    specialist_dispatcher.register("operations", run_operations_agent)
    _DEFAULT_SPECIALISTS_REGISTERED = True


__all__ = ["ensure_default_specialists_registered", "run_specialist_agent"]
