"""Deterministic formatting and validation for Supervisor subtask plans."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config.settings import load_agent_settings
from rag.agent.workflows import (
    FINANCE_SKILL_BY_NAME,
    OPERATIONS_SKILL_BY_NAME,
    load_finance_skill_config,
    load_operations_skill_config,
)


SubTaskAgent = Literal["operations", "finance", "supervisor"]
_PLANNING_SETTINGS = load_agent_settings().planning


class SubTask(BaseModel):
    """One atomic conclusion with exactly one evidence owner and primary skill."""

    id: str = Field(
        min_length=2,
        max_length=_PLANNING_SETTINGS.max_subtask_id_length,
        pattern=r"^t[1-9][0-9]*$",
        description="Sequential subtask identifier such as t1, t2, or t3.",
    )
    question: str = Field(
        min_length=_PLANNING_SETTINGS.min_subtask_question_length,
        max_length=_PLANNING_SETTINGS.max_subtask_question_length,
        description=(
            "A self-contained business question preserving the user's metric, scope, "
            "period, filters, and comparison intent."
        ),
    )
    agent: SubTaskAgent = Field(
        description="The single evidence owner: operations, finance, or supervisor."
    )
    skill: str = Field(
        min_length=_PLANNING_SETTINGS.min_skill_name_length,
        max_length=_PLANNING_SETTINGS.max_skill_name_length,
        description=(
            "One exact skill name from the selected agent's injected catalog; use "
            "search_knowledge for a supervisor-owned knowledge subtask."
        ),
    )


class FormatSubTaskInput(BaseModel):
    """The Supervisor's complete subtask plan for one user request."""

    sub_tasks: list[SubTask] = Field(
        min_length=1,
        max_length=_PLANNING_SETTINGS.max_subtasks_per_request,
        description=(
            "The minimum complete set of non-overlapping atomic subtasks, ordered as "
            "they should be executed within each specialist."
        ),
    )


def _plan_runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    state = configurable.get("subtask_plan_runtime_state")
    if not isinstance(state, dict):
        state = {"formatted": False, "sub_tasks": [], "groups": {}}
        configurable["subtask_plan_runtime_state"] = state
    return state


def _skill_error(item: SubTask) -> str | None:
    if item.agent == "operations":
        allowed = OPERATIONS_SKILL_BY_NAME
    elif item.agent == "finance":
        allowed = FINANCE_SKILL_BY_NAME
    else:
        allowed = {"search_knowledge": object()}
    if item.skill not in allowed:
        return (
            f"Subtask {item.id} assigns unknown skill {item.skill!r} to "
            f"{item.agent}. Allowed skills: {', '.join(allowed)}."
        )
    return None


@tool(args_schema=FormatSubTaskInput)
async def format_sub_task(
    sub_tasks: list[SubTask],
    config: RunnableConfig,
) -> str:
    """Validate and store one complete atomic subtask plan before delegation."""

    state = _plan_runtime_state(config)
    if state.get("formatted") is True:
        return json.dumps(
            {
                "success": False,
                "tool": "format_sub_task",
                "error_type": "subtask_plan_already_formatted",
                "error": (
                    "The subtask plan is already fixed for this request. Dispatch the "
                    "stored groups instead of formatting another plan."
                ),
                "sub_tasks": state.get("sub_tasks") or [],
                "groups": state.get("groups") or {},
            },
            ensure_ascii=False,
        )

    normalized: list[dict[str, str]] = []
    errors: list[str] = []
    seen_questions: set[str] = set()
    for index, raw_item in enumerate(sub_tasks, start=1):
        item = raw_item if isinstance(raw_item, SubTask) else SubTask.model_validate(raw_item)
        expected_id = f"t{index}"
        if item.id != expected_id:
            errors.append(
                f"Subtask IDs must be sequential in list order; expected {expected_id}, "
                f"received {item.id}."
            )
        question = " ".join(item.question.split())
        question_key = question.casefold().rstrip("?？。")
        if question_key in seen_questions:
            errors.append(f"Subtask {item.id} duplicates another subtask question.")
        seen_questions.add(question_key)
        skill_error = _skill_error(item)
        if skill_error:
            errors.append(skill_error)
        normalized.append(
            {
                "id": item.id,
                "question": question,
                "agent": item.agent,
                "skill": item.skill,
                "status": "pending",
            }
        )

    limits = {
        "operations": load_operations_skill_config().max_skills_per_task,
        "finance": load_finance_skill_config().max_skills_per_task,
    }
    for agent_name, maximum in limits.items():
        selected = {
            item["skill"] for item in normalized if item["agent"] == agent_name
        }
        if len(selected) > maximum:
            errors.append(
                f"{agent_name.title()} was assigned {len(selected)} distinct skills, "
                f"exceeding its per-task limit of {maximum}."
            )

    supervisor_tasks = [
        item for item in normalized if item["agent"] == "supervisor"
    ]
    if len(supervisor_tasks) > _PLANNING_SETTINGS.max_supervisor_knowledge_subtasks:
        errors.append(
            "Supervisor-owned knowledge subtasks exceed the configured limit of "
            f"{_PLANNING_SETTINGS.max_supervisor_knowledge_subtasks}; combine closely "
            "related policy questions."
        )

    if errors:
        return json.dumps(
            {
                "success": False,
                "tool": "format_sub_task",
                "error_type": "invalid_subtask_plan",
                "errors": errors,
                "sub_tasks": normalized,
            },
            ensure_ascii=False,
        )

    groups = {
        agent_name: [
            item["id"] for item in normalized if item["agent"] == agent_name
        ]
        for agent_name in ("operations", "finance", "supervisor")
    }
    groups = {name: ids for name, ids in groups.items() if ids}
    state.update({"formatted": True, "sub_tasks": normalized, "groups": groups})
    return json.dumps(
        {
            "success": True,
            "tool": "format_sub_task",
            "sub_tasks": normalized,
            "groups": groups,
            "instruction": (
                "Dispatch each non-empty specialist group no more than "
                f"{_PLANNING_SETTINGS.max_delegations_per_specialist} time(s) using its exact "
                "task IDs. Run independent agent groups in the same tool-call turn. For "
                "a supervisor group, call search_knowledge with that subtask's question."
            ),
        },
        ensure_ascii=False,
    )


__all__ = ["FormatSubTaskInput", "SubTask", "format_sub_task"]
