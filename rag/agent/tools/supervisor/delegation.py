"""Extensible specialist delegation tools used by the supervisor."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Awaitable, Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from observability import logger


SpecialistHandler = Callable[
    [str, RunnableConfig | None], Awaitable[dict[str, object]]
]


class DelegationInput(BaseModel):
    task: str = Field(
        min_length=3,
        max_length=1200,
        description="A self-contained specialist task with period, metrics, and filters.",
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


@tool(args_schema=DelegationInput)
async def delegate_finance(task: str, config: RunnableConfig) -> str:
    """Delegate revenue, margin, expense, refund, or cash analysis to Finance."""

    if not _claim_delegation(config, "finance"):
        return _duplicate_delegation_result("finance")
    started_at = perf_counter()
    logger.tool_event(status="started", tool_name="delegate_finance")
    result = await specialist_dispatcher.dispatch("finance", task, config)
    logger.tool_event(
        status="completed",
        tool_name="delegate_finance",
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        specialist_status=result.get("status"),
    )
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=DelegationInput)
async def delegate_operations(task: str, config: RunnableConfig) -> str:
    """Delegate sales, inventory, customer, refund, or service analysis to Operations."""

    if not _claim_delegation(config, "operations"):
        return _duplicate_delegation_result("operations")
    started_at = perf_counter()
    logger.tool_event(status="started", tool_name="delegate_operations")
    result = await specialist_dispatcher.dispatch("operations", task, config)
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
