"""Run specialists and register them with the supervisor dispatcher."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from observability import logger
from rag.agent.middleware import content_text
from rag.agent.specialists.graph import (
    SpecialistName,
    build_specialist_graph,
    get_default_specialist_graph,
)
from rag.agent.tools.registry import ToolRegistry, default_tool_registry
from rag.agent.validation import validate_specialist_evidence
from rag.agent.workflows import load_agent_runtime_config


def _collect_tool_payloads(messages: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        artifact = getattr(message, "artifact", None)
        if isinstance(artifact, dict):
            payload = dict(artifact)
        elif isinstance(message.content, str):
            try:
                payload = json.loads(message.content)
            except json.JSONDecodeError:
                continue
        else:
            continue
        if isinstance(payload, dict):
            tool_name = getattr(message, "name", None)
            if isinstance(tool_name, str) and tool_name:
                payload.setdefault("tool", tool_name)
            payloads.append(payload)
    return payloads


def _collect_sources(tool_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in tool_payloads:
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


def _assigned_sub_tasks(task: str, agent_name: SpecialistName) -> list[dict[str, str]]:
    """Read the immutable Supervisor task packet passed through delegation."""

    try:
        packet = json.loads(task)
    except json.JSONDecodeError:
        return []
    if not isinstance(packet, dict) or packet.get("agent") != agent_name:
        return []
    items = packet.get("sub_tasks")
    if not isinstance(items, list):
        return []
    return [
        {
            "id": str(item.get("id") or ""),
            "question": str(item.get("question") or ""),
            "agent": str(item.get("agent") or ""),
            "skill": str(item.get("skill") or ""),
        }
        for item in items
        if isinstance(item, dict)
    ]


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
    if graph is not None:
        active_graph = graph
    elif tool_registry is None or registry is default_tool_registry:
        active_graph = get_default_specialist_graph(agent_name)
    else:
        active_graph = build_specialist_graph(agent_name, tool_registry=registry)
    runtime_config = load_agent_runtime_config()
    assigned_sub_tasks = _assigned_sub_tasks(task, agent_name)
    assigned_skills = list(
        dict.fromkeys(
            item["skill"] for item in assigned_sub_tasks if item.get("skill")
        )
    )
    progress_items = {
        item["id"]: {
            **item,
            "status": "pending",
        }
        for item in assigned_sub_tasks
        if item.get("id")
    }
    child_config: RunnableConfig = dict(config or {})
    child_config["run_name"] = f"{agent_name}-agent"
    child_config["recursion_limit"] = runtime_config.specialist.recursion_limit
    child_config["tags"] = [agent_name, "specialist"]
    configurable = dict(child_config.get("configurable") or {})
    configurable.update(
        {
            "agent_name": agent_name,
            "sql_runtime_state": {
                "attempts": 0,
                "in_flight": False,
                "approval_denied": False,
                "successful_queries": 0,
                "successful_rows": 0,
                "successful_result_chars": 0,
            },
            "review_runtime_state": {
                "semantic_calls": 0,
                "semantic_in_flight": False,
                "other_comment_calls": 0,
                "other_comment_in_flight": False,
                "review_ids": [],
                "primary_product_name": None,
                "primary_product_category": None,
                "comparison_mode": False,
            },
            "ticket_problem_runtime_state": {
                "calls": 0,
                "in_flight": False,
            },
            "finance_metric_runtime_state": {
                "calls": {},
                "in_flight": [],
            },
            "product_resolution_runtime_state": {
                "attempts": 0,
                "in_flight": False,
                "resolved": False,
                "accepted_product_names": [],
            },
            "campaign_resolution_runtime_state": {
                "attempts": 0,
                "in_flight": False,
                "resolved": False,
                "accepted_campaign_names": [],
            },
            "skill_runtime_state": {
                "selected_skills": [],
                "assigned_skills": assigned_skills,
                "loaded": False,
            },
            "subtask_progress_runtime_state": {
                "order": list(progress_items),
                "items": progress_items,
            },
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
    tool_payloads = _collect_tool_payloads(messages)
    sources = _collect_sources(tool_payloads)
    cancelled_query = next(
        (
            payload
            for payload in tool_payloads
            if payload.get("error_type") in {"user_rejected", "approval_timeout"}
        ),
        None,
    )
    validation = validate_specialist_evidence(
        agent_name,
        answer,
        tool_payloads,
        sources,
        assigned_sub_tasks=assigned_sub_tasks,
    )
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "agent.completed",
        component="agent",
        agent_name=agent_name,
        duration_ms=duration_ms,
        evidence_count=len(sources),
        validation_status="passed" if validation["valid"] else "failed",
        validation_error_count=len(validation["errors"]),
    )
    return {
        "status": (
            "completed"
            if validation["valid"]
            else "query_cancelled"
            if cancelled_query is not None
            else "invalid_evidence"
        ),
        "agent": agent_name,
        "answer": answer,
        "assigned_sub_tasks": assigned_sub_tasks,
        "sources": sources,
        "validation": validation,
        "query_cancellation": (
            {
                "error_type": cancelled_query.get("error_type"),
                "message": cancelled_query.get("error"),
                "executed": False,
            }
            if cancelled_query is not None
            else None
        ),
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
