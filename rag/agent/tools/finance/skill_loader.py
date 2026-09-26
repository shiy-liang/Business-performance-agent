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
    load_finance_skill_config,
)


class LoadFinanceSkillsInput(BaseModel):
    """One complete, ordered Finance skill selection for the task packet."""

    skill_names: list[str] = Field(
        min_length=1,
        description=(
            "Unique Finance skill names assigned by the Supervisor. Submit the "
            "ordered union of all assigned skills together in one call."
        ),
    )


def _skill_runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("skill_runtime_state")
    if not isinstance(state, dict):
        state = {
            "selected_skills": [],
            "loaded": False,
        }
        configurable["skill_runtime_state"] = state
    return state


def selected_finance_skills(config: RunnableConfig) -> tuple[str, ...]:
    """Return Finance skills already selected for this run."""

    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return ()
    state = configurable.get("skill_runtime_state")
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
    """Load all Supervisor-assigned Finance skills before evidence tools."""

    tool_name = "load_finance_skills"
    started_at = perf_counter()
    logger.tool_event(
        status="started",
        tool_name=tool_name,
        requested_skill_count=len(skill_names),
    )
    settings = load_finance_skill_config()
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
                "error": "Each skill may be selected only once.",
            },
            started_at=started_at,
        )
    if len(selected) > settings.max_skills_per_task:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "skill_limit",
                "error": (
                    "The skill selection exceeds the configured maximum of "
                    f"{settings.max_skills_per_task}."
                ),
                "max_skills_per_task": settings.max_skills_per_task,
            },
            started_at=started_at,
        )

    state = _skill_runtime_state(config)
    assigned = state.get("assigned_skills")
    if isinstance(assigned, list) and assigned and selected != assigned:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "assigned_skill_mismatch",
                "error": (
                    "Load exactly the ordered union of Supervisor-assigned skills. "
                    "Do not add, omit, or reroute skills."
                ),
                "assigned_skills": assigned,
                "received_skills": selected,
            },
            started_at=started_at,
        )
    if state.get("loaded") is True:
        return _response(
            {
                "success": False,
                "tool": tool_name,
                "error_type": "skills_already_loaded",
                "error": "Skill instructions were already loaded for this task.",
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
            "max_skills_per_task": settings.max_skills_per_task,
            "instruction": (
                "The selected skill bodies are authoritative for their assigned "
                "subtasks. Follow each body only for the matching subtask."
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
