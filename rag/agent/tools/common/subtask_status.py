"""Backend-governed real-time status transitions for specialist subtasks."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field


SubTaskStatus = Literal["running", "completed", "blocked", "empty"]
TERMINAL_STATUSES = frozenset({"completed", "blocked", "empty"})


class UpdateSubTaskStatusInput(BaseModel):
    """One explicit, validated state transition for an assigned subtask."""

    subtask_id: str = Field(
        pattern=r"^t[1-9][0-9]*$",
        description="Exact ID from the delegated subtask packet.",
    )
    status: SubTaskStatus = Field(
        description=(
            "Use running immediately before work starts; use completed, blocked, "
            "or empty immediately after that subtask finishes."
        )
    )
    message: str = Field(
        min_length=2,
        max_length=240,
        description="A short public progress description without private reasoning.",
    )


def _progress_state(config: RunnableConfig) -> dict[str, Any] | None:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    state = configurable.get("subtask_progress_runtime_state")
    return state if isinstance(state, dict) else None


def _error(
    *,
    agent_name: str,
    subtask_id: str,
    error_type: str,
    message: str,
    current_status: str | None = None,
) -> str:
    return json.dumps(
        {
            "success": False,
            "agent": agent_name,
            "tool": "update_sub_task_status",
            "subtask_id": subtask_id,
            "error_type": error_type,
            "error": message,
            "current_status": current_status,
            "sources": [],
        },
        ensure_ascii=False,
    )


def _update_shared_plan(
    config: RunnableConfig,
    subtask_id: str,
    status: SubTaskStatus,
) -> None:
    configurable = config.get("configurable")
    plan_state = (
        configurable.get("subtask_plan_runtime_state")
        if isinstance(configurable, dict)
        else None
    )
    if not isinstance(plan_state, dict):
        return
    for item in plan_state.get("sub_tasks") or []:
        if isinstance(item, dict) and item.get("id") == subtask_id:
            item["status"] = status
            return


@tool(args_schema=UpdateSubTaskStatusInput)
async def update_sub_task_status(
    subtask_id: str,
    status: SubTaskStatus,
    message: str,
    config: RunnableConfig,
) -> str:
    """Move one assigned subtask through pending, running, and a terminal state."""

    state = _progress_state(config)
    configurable = config.get("configurable")
    agent_name = (
        str(configurable.get("agent_name") or "specialist")
        if isinstance(configurable, dict)
        else "specialist"
    )
    if state is None:
        return _error(
            agent_name=agent_name,
            subtask_id=subtask_id,
            error_type="subtask_state_missing",
            message="No delegated subtask state is available for this run.",
        )
    order = state.get("order")
    items = state.get("items")
    if not isinstance(order, list) or not isinstance(items, dict):
        return _error(
            agent_name=agent_name,
            subtask_id=subtask_id,
            error_type="subtask_state_invalid",
            message="The delegated subtask state is invalid.",
        )
    item = items.get(subtask_id)
    if not isinstance(item, dict) or subtask_id not in order:
        return _error(
            agent_name=agent_name,
            subtask_id=subtask_id,
            error_type="unknown_subtask",
            message="The subtask ID is not assigned to this specialist.",
        )

    current_status = str(item.get("status") or "pending")
    if status == "running":
        if current_status != "pending":
            return _error(
                agent_name=agent_name,
                subtask_id=subtask_id,
                error_type="invalid_subtask_transition",
                message="Only a pending subtask can transition to running.",
                current_status=current_status,
            )
        task_index = order.index(subtask_id)
        unfinished_predecessors = [
            task_id
            for task_id in order[:task_index]
            if str((items.get(task_id) or {}).get("status")) not in TERMINAL_STATUSES
        ]
        running_tasks = [
            task_id
            for task_id in order
            if str((items.get(task_id) or {}).get("status")) == "running"
        ]
        if unfinished_predecessors or running_tasks:
            return _error(
                agent_name=agent_name,
                subtask_id=subtask_id,
                error_type="subtask_order_violation",
                message=(
                    "Subtasks must run sequentially; finish the current and all "
                    "preceding subtasks before starting this one."
                ),
                current_status=current_status,
            )
    elif status in TERMINAL_STATUSES and current_status != "running":
        return _error(
            agent_name=agent_name,
            subtask_id=subtask_id,
            error_type="invalid_subtask_transition",
            message="Only the running subtask can transition to a terminal status.",
            current_status=current_status,
        )

    item["status"] = status
    _update_shared_plan(config, subtask_id, status)
    event = {
        "agent": agent_name,
        "subtask_id": subtask_id,
        "question": str(item.get("question") or ""),
        "skill": str(item.get("skill") or ""),
        "status": status,
        "message": " ".join(message.split()),
    }
    await adispatch_custom_event("subtask_status", event, config=config)
    return json.dumps(
        {
            "success": True,
            "tool": "update_sub_task_status",
            **event,
            "sources": [],
        },
        ensure_ascii=False,
    )


__all__ = [
    "SubTaskStatus",
    "TERMINAL_STATUSES",
    "UpdateSubTaskStatusInput",
    "update_sub_task_status",
]
