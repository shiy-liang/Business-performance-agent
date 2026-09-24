"""Progressive-disclosure skill catalog and workflow configuration."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parents[1]
SKILL_ROOT = AGENT_ROOT / "skills"
DEFAULT_AGENT_CONFIG_PATH = PROJECT_ROOT / "config" / "agent.yml"


class WorkflowConfigError(ValueError):
    """Raised when workflow routing configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class OperationsWorkflowConfig:
    max_workflows_per_task: int


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    name: str
    title: str
    path: Path


OPERATIONS_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        "product_review_retrieval",
        "Product Review Retrieval",
        SKILL_ROOT / "operations" / "product_review_retrieval.md",
    ),
    SkillDefinition(
        "product_purchase_rate",
        "Product Purchase Rate",
        SKILL_ROOT / "operations" / "product_purchase_rate.md",
    ),
    SkillDefinition(
        "product_like_rate",
        "Product Like Rate",
        SKILL_ROOT / "operations" / "product_like_rate.md",
    ),
    SkillDefinition(
        "product_bottom_rates",
        "Product Bottom Rates",
        SKILL_ROOT / "operations" / "product_bottom_rates.md",
    ),
    SkillDefinition(
        "product_interaction_duration",
        "Product Interaction Duration Ranking",
        SKILL_ROOT / "operations" / "product_interaction_duration.md",
    ),
    SkillDefinition(
        "sql_query",
        "Operations SQL Query",
        SKILL_ROOT / "operations" / "sql_query.md",
    ),
)
OPERATIONS_SKILL_BY_NAME = {skill.name: skill for skill in OPERATIONS_SKILLS}
OPERATIONS_DEDICATED_SKILL_NAMES = frozenset(
    skill.name for skill in OPERATIONS_SKILLS if skill.name != "sql_query"
)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowConfigError(f"{name} must be a mapping")
    return value


@lru_cache(maxsize=1)
def load_operations_workflow_config(
    path: Path = DEFAULT_AGENT_CONFIG_PATH,
) -> OperationsWorkflowConfig:
    """Load and validate Operations workflow routing limits."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowConfigError(f"Agent config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise WorkflowConfigError(f"Invalid agent YAML in {path}: {exc}") from exc

    root = _mapping(raw, "agent config")
    operations = _mapping(root.get("operations"), "operations")
    maximum = operations.get("max_workflows_per_task")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
        raise WorkflowConfigError(
            "operations.max_workflows_per_task must be a positive integer"
        )
    if maximum > len(OPERATIONS_DEDICATED_SKILL_NAMES):
        raise WorkflowConfigError(
            "operations.max_workflows_per_task cannot exceed the number of "
            "dedicated Operations skills"
        )
    return OperationsWorkflowConfig(max_workflows_per_task=maximum)


@lru_cache(maxsize=None)
def read_skill_body(skill_name: str) -> str:
    """Read one allow-listed skill body from its version-controlled Markdown file."""

    definition = OPERATIONS_SKILL_BY_NAME.get(skill_name)
    if definition is None:
        raise KeyError(f"Unknown Operations skill: {skill_name}")
    try:
        return definition.path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise WorkflowConfigError(
            f"Unable to load Operations skill: {definition.path}"
        ) from exc


def _routing_description(markdown: str) -> str:
    """Extract only the first applicability section, not the workflow body."""

    lines = markdown.splitlines()
    description: list[str] = []
    in_applicability = False
    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if in_applicability:
                break
            in_applicability = heading in {"trigger", "use this skill for"}
            continue
        if in_applicability and line.strip():
            description.append(line.strip())
    return " ".join(description)


@lru_cache(maxsize=1)
def build_operations_skill_catalog() -> str:
    """Build the compact first-layer catalog shown before any skill is selected."""

    entries = []
    for skill in OPERATIONS_SKILLS:
        description = _routing_description(read_skill_body(skill.name))
        entries.append(f"- `{skill.name}` — **{skill.title}**: {description}")
    return "\n".join(entries)


def load_operations_skill_bodies(skill_names: list[str]) -> dict[str, str]:
    """Load selected bodies, adding SQL safety only for the generic fallback."""

    bodies = {name: read_skill_body(name) for name in skill_names}
    if "sql_query" in bodies:
        bodies["sql_safety"] = (
            SKILL_ROOT / "common" / "sql_safety.md"
        ).read_text(encoding="utf-8").strip()
    return bodies


__all__ = [
    "OPERATIONS_DEDICATED_SKILL_NAMES",
    "OPERATIONS_SKILLS",
    "OPERATIONS_SKILL_BY_NAME",
    "OperationsWorkflowConfig",
    "SkillDefinition",
    "WorkflowConfigError",
    "build_operations_skill_catalog",
    "load_operations_skill_bodies",
    "load_operations_workflow_config",
    "read_skill_body",
]
