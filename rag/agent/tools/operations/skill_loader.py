"""On-demand Operations skill loading for progressive prompt disclosure."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from rag.agent.workflows import (
    OPERATIONS_SKILL_BY_NAME,
    load_operations_skill_bodies,
    load_operations_workflow_config,
)


class LoadOperationsSkillsInput(BaseModel):
    """One complete, ordered workflow selection for the delegated task."""

    skill_names: list[str] = Field(
        min_length=1,
        description=(
            "Unique Operations skill names selected from the injected skill catalog. "
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


def selected_operations_skills(config: RunnableConfig) -> tuple[str, ...]:
    """Return skills already selected for this run without mutating the state."""

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


@tool(args_schema=LoadOperationsSkillsInput)
async def load_operations_skills(
    skill_names: list[str],
    config: RunnableConfig,
) -> str:
    """Load full instructions for selected Operations workflows before using evidence tools."""

    settings = load_operations_workflow_config()
    selected = list(dict.fromkeys(skill_names))
    unknown = [name for name in selected if name not in OPERATIONS_SKILL_BY_NAME]
    if unknown:
        return json.dumps(
            {
                "success": False,
                "error_type": "unknown_skill",
                "error": "Unknown Operations skill selection.",
                "unknown_skills": unknown,
                "available_skills": list(OPERATIONS_SKILL_BY_NAME),
            },
            ensure_ascii=False,
        )
    if len(selected) != len(skill_names):
        return json.dumps(
            {
                "success": False,
                "error_type": "duplicate_skill",
                "error": "Each workflow may be selected only once.",
            },
            ensure_ascii=False,
        )
    if len(selected) > settings.max_workflows_per_task:
        return json.dumps(
            {
                "success": False,
                "error_type": "workflow_limit",
                "error": (
                    "The workflow selection exceeds the configured maximum of "
                    f"{settings.max_workflows_per_task}."
                ),
                "max_workflows_per_task": settings.max_workflows_per_task,
            },
            ensure_ascii=False,
        )
    if "sql_query" in selected and len(selected) > 1:
        return json.dumps(
            {
                "success": False,
                "error_type": "generic_workflow_conflict",
                "error": (
                    "sql_query is a fallback and cannot be selected with a dedicated "
                    "workflow. Keep the matching dedicated workflows only."
                ),
            },
            ensure_ascii=False,
        )

    state = _workflow_runtime_state(config)
    if state.get("generic_workflow_started") is True and "sql_query" not in selected:
        return json.dumps(
            {
                "success": False,
                "error_type": "generic_workflow_already_started",
                "error": (
                    "A dedicated workflow cannot be selected after the generic SQL "
                    "fallback has started."
                ),
            },
            ensure_ascii=False,
        )
    if state.get("loaded") is True:
        return json.dumps(
            {
                "success": False,
                "error_type": "skills_already_loaded",
                "error": "Workflow instructions were already loaded for this task.",
                "selected_skills": state.get("selected_skills") or [],
            },
            ensure_ascii=False,
        )

    state["selected_skills"] = selected
    state["loaded"] = True
    return json.dumps(
        {
            "success": True,
            "tool": "load_operations_skills",
            "selected_skills": selected,
            "selected_skill_titles": [
                OPERATIONS_SKILL_BY_NAME[name].title for name in selected
            ],
            "max_workflows_per_task": settings.max_workflows_per_task,
            "instruction": (
                "The selected skill bodies below are the authoritative workflow "
                "instructions for this delegated task. Follow all selected bodies."
            ),
            "skill_bodies": load_operations_skill_bodies(selected),
        },
        ensure_ascii=False,
    )


__all__ = [
    "LoadOperationsSkillsInput",
    "load_operations_skills",
    "selected_operations_skills",
]
