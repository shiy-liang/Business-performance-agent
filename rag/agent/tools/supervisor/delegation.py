"""Extensible specialist delegation tools used by the supervisor."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Awaitable, Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from observability import logger


SpecialistHandler = Callable[
    [str, RunnableConfig | None], Awaitable[dict[str, object]]
]


class DelegationInput(BaseModel):
    task_ids: list[str] = Field(
        min_length=1,
        max_length=8,
        description=(
            "The exact ordered IDs of every formatted subtask assigned to this "
            "specialist. Do not rewrite task questions or skill assignments."
        ),
    )


class SpecialistDispatcher:
    """Register real specialist graphs without changing the supervisor contract."""

    def __init__(self) -> None:
        self._handlers: dict[str, SpecialistHandler] = {}

    def register(self, name: str, handler: SpecialistHandler) -> None:
        self._handlers[name] = handler

    async def dispatch(
        self,
        name: str,
        task: str,
        config: RunnableConfig | None = None,
    ) -> dict[str, object]:
        handler = self._handlers.get(name)
        if handler is None:
            return {
                "status": "not_connected",
                "agent": name,
                "message": (
                    f"The {name} specialist is reserved by the supervisor contract "
                    "but is not connected in this prototype."
                ),
            }
        return await handler(task, config)


specialist_dispatcher = SpecialistDispatcher()


def _claim_delegation(config: RunnableConfig, agent_name: str) -> bool:
    """Allow one delegation per specialist for the current supervisor run."""

    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    runtime_state = configurable.get("delegation_runtime_state")
    if not isinstance(runtime_state, dict):
        runtime_state = {}
        configurable["delegation_runtime_state"] = runtime_state
    if runtime_state.get(agent_name) is True:
        return False
    runtime_state[agent_name] = True
    return True


def _duplicate_delegation_result(agent_name: str) -> str:
    return json.dumps(
        {
            "status": "duplicate_blocked",
            "agent": agent_name,
            "message": (
                f"The {agent_name} specialist was already delegated for this request. "
                "Use the existing specialist evidence and complete the answer."
            ),
            "sources": [],
        },
        ensure_ascii=False,
    )


def _delegation_error(
    agent_name: str,
    error_type: str,
    message: str,
    **details: Any,
) -> str:
    return json.dumps(
        {
            "status": "invalid_delegation",
            "agent": agent_name,
            "error_type": error_type,
            "message": message,
            "sources": [],
            **details,
        },
        ensure_ascii=False,
    )


def _task_packet(
    config: RunnableConfig,
    agent_name: str,
    task_ids: list[str],
) -> tuple[str | None, str | None]:
    """Resolve exact task IDs from the fixed Supervisor plan."""

    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None, _delegation_error(
            agent_name,
            "subtask_plan_missing",
            "format_sub_task must succeed before specialist delegation.",
        )
    plan_state = configurable.get("subtask_plan_runtime_state")
    if not isinstance(plan_state, dict) or plan_state.get("formatted") is not True:
        return None, _delegation_error(
            agent_name,
            "subtask_plan_missing",
            "format_sub_task must succeed before specialist delegation.",
        )
    planned = [
        item
        for item in plan_state.get("sub_tasks") or []
        if isinstance(item, dict) and item.get("agent") == agent_name
    ]
    expected_ids = [str(item.get("id")) for item in planned]
    supplied_ids = [str(item) for item in task_ids]
    if supplied_ids != expected_ids:
        return None, _delegation_error(
            agent_name,
            "subtask_group_mismatch",
            (
                "Delegate exactly the complete formatted group in its original order; "
                "do not omit, add, duplicate, or reorder task IDs."
            ),
            expected_task_ids=expected_ids,
            received_task_ids=supplied_ids,
        )
    if not planned:
        return None, _delegation_error(
            agent_name,
            "empty_subtask_group",
            f"The formatted plan contains no {agent_name} subtasks.",
        )
    packet = {
        "agent": agent_name,
        "sub_tasks": planned,
        "execution_contract": (
            "Use each assigned primary skill only for its matching subtask. Load the "
            "union of assigned skills once, execute subtasks in listed order, and "
            "return one evidence section per subtask. Do not add or reroute tasks."
        ),
    }
    return json.dumps(packet, ensure_ascii=False), None


def _record_subtask_statuses(
    config: RunnableConfig,
    result: dict[str, object],
) -> None:
    """Copy validated specialist status markers back into the fixed plan state."""

    validation = result.get("validation")
    if not isinstance(validation, dict):
        return
    statuses = validation.get("subtask_statuses")
    if not isinstance(statuses, dict):
        return
    configurable = config.get("configurable")
    plan_state = (
        configurable.get("subtask_plan_runtime_state")
        if isinstance(configurable, dict)
        else None
    )
    if not isinstance(plan_state, dict):
        return
    for item in plan_state.get("sub_tasks") or []:
        if not isinstance(item, dict):
            continue
        status = statuses.get(str(item.get("id") or ""))
        if status in {"completed", "blocked", "empty"}:
            item["status"] = status


@tool(args_schema=DelegationInput)
async def delegate_finance(task_ids: list[str], config: RunnableConfig) -> str:
    """Run all formatted Finance subtasks in one Finance Agent invocation."""

    task, error = _task_packet(config, "finance", task_ids)
    if error is not None or task is None:
        return error or ""
    if not _claim_delegation(config, "finance"):
        return _duplicate_delegation_result("finance")
    started_at = perf_counter()
    logger.tool_event(status="started", tool_name="delegate_finance")
    result = await specialist_dispatcher.dispatch("finance", task, config)
    _record_subtask_statuses(config, result)
    logger.tool_event(
        status="completed",
        tool_name="delegate_finance",
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        specialist_status=result.get("status"),
    )
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=DelegationInput)
async def delegate_operations(task_ids: list[str], config: RunnableConfig) -> str:
    """Run all formatted Operations subtasks in one Operations Agent invocation."""

    task, error = _task_packet(config, "operations", task_ids)
    if error is not None or task is None:
        return error or ""
    if not _claim_delegation(config, "operations"):
        return _duplicate_delegation_result("operations")
    started_at = perf_counter()
    logger.tool_event(status="started", tool_name="delegate_operations")
    result = await specialist_dispatcher.dispatch("operations", task, config)
    _record_subtask_statuses(config, result)
    logger.tool_event(
        status="completed",
        tool_name="delegate_operations",
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        specialist_status=result.get("status"),
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = [
    "SpecialistDispatcher",
    "delegate_finance",
    "delegate_operations",
    "specialist_dispatcher",
]
