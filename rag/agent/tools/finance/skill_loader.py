"""On-demand Finance skill loading for progressive prompt disclosure."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from observability import logger
from rag.agent.workflows import (
    FINANCE_SKILL_BY_NAME,
    load_finance_skill_bodies,
    load_finance_workflow_config,
)


class LoadFinanceSkillsInput(BaseModel):
    """One complete, ordered Finance workflow selection for the task."""

    skill_names: list[str] = Field(
        min_length=1,
        description=(
            "Unique Finance skill names selected from the injected skill catalog. "
            "Submit all matching dedicated skills together in one call."
        ),
    )


def _workflow_runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("workflow_runtime_state")
    if not isinstance(state, dict):
        state = {
            "selected_skills": [],
            "loaded": False,
            "generic_workflow_started": False,
        }
        configurable["workflow_runtime_state"] = state
    return state


def selected_finance_skills(config: RunnableConfig) -> tuple[str, ...]:
    """Return Finance skills already selected for this run."""

    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return ()
    state = configurable.get("workflow_runtime_state")
    if not isinstance(state, dict):
        return ()
    selected = state.get("selected_skills")
    if not isinstance(selected, list):
        return ()
    return tuple(str(item) for item in selected)


def _response(
    payload: dict[str, Any],
    *,
    started_at: float,
) -> str:
    logger.tool_event(
        status="completed",
        tool_name="load_finance_skills",
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
        success=payload.get("success") is True,
        selected_skill_count=len(payload.get("selected_skills") or []),
        error_type=payload.get("error_type"),
    )
    return json.dumps(payload, ensure_ascii=False)


@tool(args_schema=LoadFinanceSkillsInput)
async def load_finance_skills(
    skill_names: list[str],
    config: RunnableConfig,
) -> str:
    """Load full instructions for selected Finance workflows before evidence tools."""

    tool_name = "load_finance_skills"
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        requested_skill_count=len(skill_names),
    )
    settings = load_finance_workflow_config()
    selected = list(dict.fromkeys(skill_names))
    unknown = [name for name in selected if name not in FINANCE_SKILL_BY_NAME]
    if unknown:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "unknown_skill",
                "error": "Unknown Finance skill selection.",
                "unknown_skills": unknown,
                "available_skills": list(FINANCE_SKILL_BY_NAME),
            },
            started_at=started_at,
        )
    if len(selected) != len(skill_names):
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "duplicate_skill",
                "error": "Each workflow may be selected only once.",
            },
            started_at=started_at,
        )
    if len(selected) > settings.max_workflows_per_task:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "workflow_limit",
                "error": (
                    "The workflow selection exceeds the configured maximum of "
                    f"{settings.max_workflows_per_task}."
                ),
                "max_workflows_per_task": settings.max_workflows_per_task,
            },
            started_at=started_at,
        )
    if "sql_query" in selected and len(selected) > 1:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "generic_workflow_conflict",
                "error": (
                    "sql_query is a fallback and cannot be selected with a "
                    "dedicated workflow."
                ),
            },
            started_at=started_at,
        )

    state = _workflow_runtime_state(config)
    if state.get("generic_workflow_started") is True and "sql_query" not in selected:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "generic_workflow_already_started",
                "error": (
                    "A dedicated workflow cannot be selected after the generic "
                    "SQL fallback has started."
                ),
            },
            started_at=started_at,
        )
    if state.get("loaded") is True:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "skills_already_loaded",
                "error": "Workflow instructions were already loaded for this task.",
                "selected_skills": state.get("selected_skills") or [],
            },
            started_at=started_at,
        )

    state["selected_skills"] = selected
    state["loaded"] = True
    return _response(
        {
            "success": True,
            "tool": tool_name,
            "selected_skills": selected,
            "selected_skill_titles": [
                FINANCE_SKILL_BY_NAME[name].title for name in selected
            ],
            "max_workflows_per_task": settings.max_workflows_per_task,
            "instruction": (
                "The selected skill bodies below are the authoritative workflow "
                "instructions for this delegated task. Follow all selected bodies."
            ),
            "skill_bodies": load_finance_skill_bodies(selected),
        },
        started_at=started_at,
    )


__all__ = [
    "LoadFinanceSkillsInput",
    "load_finance_skills",
    "selected_finance_skills",
]
