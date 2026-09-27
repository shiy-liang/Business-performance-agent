"""Load version-controlled Markdown prompts and skills with safe injection."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping

from config.settings import render_config_template
from rag.agent.workflows import (
    build_finance_skill_catalog,
    build_operations_skill_catalog,
    load_finance_skill_config,
    load_operations_skill_config,
)


AGENT_ROOT = Path(__file__).resolve().parent
PROMPT_ROOT = AGENT_ROOT / "prompts"
SKILL_ROOT = AGENT_ROOT / "skills"


class PromptTemplateError(RuntimeError):
    """Raised when a required prompt component cannot be loaded."""


def _read(path: Path) -> str:
    try:
        return render_config_template(path.read_text(encoding="utf-8").strip())
    except OSError as exc:
        raise PromptTemplateError(f"Unable to load prompt component: {path}") from exc


def inject_template(template: str, values: Mapping[str, str]) -> str:
    """Replace explicit double-brace placeholders without interpreting Markdown."""

    rendered = template
    for name, value in values.items():
        rendered = rendered.replace("{{" + name + "}}", value)
    return rendered


@lru_cache(maxsize=1)
def load_supervisor_components() -> dict[str, str]:
    """Load the supervisor prompt and all skills used by this prototype."""

    return {
        "system": _read(PROMPT_ROOT / "supervisor" / "system.md"),
        "routing": _read(PROMPT_ROOT / "supervisor" / "routing.md"),
        "response_contract": _read(
            PROMPT_ROOT / "supervisor" / "response_contract.md"
        ),
        "business_diagnosis": _read(
            SKILL_ROOT / "supervisor" / "business_diagnosis.md"
        ),
        "task_decomposition": _read(
            SKILL_ROOT / "supervisor" / "task_decomposition.md"
        ),
        "evidence_policy": _read(SKILL_ROOT / "common" / "evidence_policy.md"),
    }


def build_supervisor_prompt(
    *,
    user_question: str,
    available_tools: str,
) -> str:
    """Compose the injectable supervisor system prompt for one user turn."""

    components = load_supervisor_components()
    task_decomposition = inject_template(
        components["task_decomposition"],
        {
            "operations_skill_catalog": build_operations_skill_catalog(),
            "finance_skill_catalog": build_finance_skill_catalog(),
        },
    )
    skills = "\n\n".join(
        (
            components["business_diagnosis"],
            task_decomposition,
            components["evidence_policy"],
        )
    )
    return inject_template(
        components["system"],
        {
            "user_question": user_question,
            "available_tools": available_tools,
            "routing_rules": components["routing"],
            "response_contract": components["response_contract"],
            "skills": skills,
        },
    )


@lru_cache(maxsize=2)
def load_specialist_components(agent_name: str) -> dict[str, str]:
    """Load static prompt parts and each specialist's routing catalog."""

    if agent_name not in {"finance", "operations"}:
        raise PromptTemplateError(f"Unsupported specialist: {agent_name}")
    return {
        "system": _read(PROMPT_ROOT / agent_name / "system.md"),
        "response_contract": _read(PROMPT_ROOT / agent_name / "response_contract.md"),
        "skill_catalog": (
            build_finance_skill_catalog()
            if agent_name == "finance"
            else build_operations_skill_catalog()
        ),
    }


def build_specialist_prompt(
    *,
    agent_name: str,
    task: str,
    available_tools: str,
) -> str:
    """Compose a domain specialist prompt with injectable SQL instructions."""

    components = load_specialist_components(agent_name)
    # Specialists use progressive disclosure: only routing metadata is in the
    # system prompt; complete selected bodies arrive later through a ToolMessage.
    settings = (
        load_finance_skill_config()
        if agent_name == "finance"
        else load_operations_skill_config()
    )
    extra_values = {
        "skill_catalog": components["skill_catalog"],
        "max_skills_per_task": str(settings.max_skills_per_task),
    }
    return inject_template(
        components["system"],
        {
            "task": task,
            "available_tools": available_tools,
            "response_contract": components["response_contract"],
            **extra_values,
        },
    )


__all__ = [
    "PromptTemplateError",
    "build_specialist_prompt",
    "build_supervisor_prompt",
    "inject_template",
    "load_specialist_components",
    "load_supervisor_components",
]
