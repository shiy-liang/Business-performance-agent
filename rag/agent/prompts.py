"""Load version-controlled Markdown prompts and skills with safe injection."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping


AGENT_ROOT = Path(__file__).resolve().parent
PROMPT_ROOT = AGENT_ROOT / "prompts"
SKILL_ROOT = AGENT_ROOT / "skills"


class PromptTemplateError(RuntimeError):
    """Raised when a required prompt component cannot be loaded."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
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
        "evidence_policy": _read(SKILL_ROOT / "common" / "evidence_policy.md"),
    }


def build_supervisor_prompt(
    *,
    user_question: str,
    available_tools: str,
) -> str:
    """Compose the injectable supervisor system prompt for one user turn."""

    components = load_supervisor_components()
    skills = "\n\n".join(
        (
            components["business_diagnosis"],
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
    """Load one specialist's prompt, response contract, and SQL skill."""

    if agent_name not in {"finance", "operations"}:
        raise PromptTemplateError(f"Unsupported specialist: {agent_name}")
    return {
        "system": _read(PROMPT_ROOT / agent_name / "system.md"),
        "response_contract": _read(PROMPT_ROOT / agent_name / "response_contract.md"),
        "sql_skill": _read(SKILL_ROOT / agent_name / "sql_query.md"),
        "sql_safety": _read(SKILL_ROOT / "common" / "sql_safety.md"),
    }


def build_specialist_prompt(
    *,
    agent_name: str,
    task: str,
    available_tools: str,
) -> str:
    """Compose a domain specialist prompt with injectable SQL instructions."""

    components = load_specialist_components(agent_name)
    skills = "\n\n".join((components["sql_skill"], components["sql_safety"]))
    return inject_template(
        components["system"],
        {
            "task": task,
            "available_tools": available_tools,
            "response_contract": components["response_contract"],
            "skills": skills,
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
