"""Progressive-disclosure skill catalogs and per-agent skill limits."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.settings import AgentSettings, load_agent_settings, render_config_template


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parents[1]
SKILL_ROOT = AGENT_ROOT / "skills"
DEFAULT_AGENT_CONFIG_PATH = PROJECT_ROOT / "config" / "agent.yml"


class SkillConfigError(ValueError):
    """Raised when skill catalog or agent runtime configuration is invalid."""


# Historical public name retained for callers outside this package.
WorkflowConfigError = SkillConfigError


@dataclass(frozen=True, slots=True)
class GraphRuntimeConfig:
    recursion_limit: int


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    supervisor: GraphRuntimeConfig
    specialist: GraphRuntimeConfig


@dataclass(frozen=True, slots=True)
class OperationsSkillConfig:
    max_skills_per_task: int

    @property
    def max_workflows_per_task(self) -> int:
        """Deprecated compatibility view of the skill limit."""

        return self.max_skills_per_task


@dataclass(frozen=True, slots=True)
class FinanceSkillConfig:
    max_skills_per_task: int

    @property
    def max_workflows_per_task(self) -> int:
        """Deprecated compatibility view of the skill limit."""

        return self.max_skills_per_task


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    name: str
    title: str
    path: Path


OPERATIONS_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        "support_ticket_problem_retrieval",
        "Support Ticket Problem Retrieval",
        SKILL_ROOT / "operations" / "support_ticket_problem_retrieval.md",
    ),
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
FINANCE_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        "net_sales",
        "Net Sales",
        SKILL_ROOT / "finance" / "net_sales.md",
    ),
    SkillDefinition(
        "gross_profit_margin",
        "Gross Profit and Gross Margin",
        SKILL_ROOT / "finance" / "gross_profit_margin.md",
    ),
    SkillDefinition(
        "product_bottom_purchase_rate",
        "Product Bottom Purchase Rate",
        SKILL_ROOT / "finance" / "product_bottom_purchase_rate.md",
    ),
    SkillDefinition(
        "sql_query",
        "Finance SQL Query",
        SKILL_ROOT / "finance" / "sql_query.md",
    ),
)
FINANCE_SKILL_BY_NAME = {skill.name: skill for skill in FINANCE_SKILLS}
FINANCE_DEDICATED_SKILL_NAMES = frozenset(
    skill.name for skill in FINANCE_SKILLS if skill.name != "sql_query"
)
OPERATIONS_SKILL_BY_NAME = {skill.name: skill for skill in OPERATIONS_SKILLS}
OPERATIONS_DEDICATED_SKILL_NAMES = frozenset(
    skill.name for skill in OPERATIONS_SKILLS if skill.name != "sql_query"
)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowConfigError(f"{name} must be a mapping")
    return value


def _positive_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WorkflowConfigError(f"{name} must be a positive integer")
    return value


def _agent_settings(path: Path) -> AgentSettings:
    if path == DEFAULT_AGENT_CONFIG_PATH:
        return load_agent_settings()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowConfigError(f"Agent config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise WorkflowConfigError(f"Invalid agent YAML in {path}: {exc}") from exc
    try:
        return AgentSettings.model_validate(raw)
    except ValueError as exc:
        raise WorkflowConfigError(f"Invalid Agent configuration in {path}: {exc}") from exc


@lru_cache(maxsize=1)
def load_agent_runtime_config(
    path: Path = DEFAULT_AGENT_CONFIG_PATH,
) -> AgentRuntimeConfig:
    """Load and validate supervisor and specialist graph runtime limits."""

    settings = _agent_settings(path)
    return AgentRuntimeConfig(
        supervisor=GraphRuntimeConfig(
            recursion_limit=settings.runtime.supervisor.recursion_limit
        ),
        specialist=GraphRuntimeConfig(
            recursion_limit=settings.runtime.specialist.recursion_limit
        ),
    )


@lru_cache(maxsize=1)
def load_operations_skill_config(
    path: Path = DEFAULT_AGENT_CONFIG_PATH,
) -> OperationsSkillConfig:
    """Load and validate the Operations per-task skill limit."""

    maximum = _agent_settings(path).operations.max_skills_per_task
    if maximum > len(OPERATIONS_SKILLS):
        raise WorkflowConfigError(
            "operations.max_skills_per_task cannot exceed the number of "
            "Operations skills"
        )
    return OperationsSkillConfig(max_skills_per_task=maximum)


@lru_cache(maxsize=1)
def load_finance_skill_config(
    path: Path = DEFAULT_AGENT_CONFIG_PATH,
) -> FinanceSkillConfig:
    """Load and validate the Finance per-task skill limit."""

    maximum = _agent_settings(path).finance.max_skills_per_task
    if maximum > len(FINANCE_SKILLS):
        raise WorkflowConfigError(
            "finance.max_skills_per_task cannot exceed the number of Finance skills"
        )
    return FinanceSkillConfig(max_skills_per_task=maximum)


# Backward-compatible import aliases for integrations that have not yet migrated.
OperationsWorkflowConfig = OperationsSkillConfig
FinanceWorkflowConfig = FinanceSkillConfig
load_operations_workflow_config = load_operations_skill_config
load_finance_workflow_config = load_finance_skill_config


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


@lru_cache(maxsize=None)
def read_finance_skill_body(skill_name: str) -> str:
    """Read one allow-listed Finance skill body."""

    definition = FINANCE_SKILL_BY_NAME.get(skill_name)
    if definition is None:
        raise KeyError(f"Unknown Finance skill: {skill_name}")
    try:
        return definition.path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise WorkflowConfigError(
            f"Unable to load Finance skill: {definition.path}"
        ) from exc


def _routing_description(markdown: str) -> str:
    """Extract only the first applicability section, not the procedure body."""

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


@lru_cache(maxsize=1)
def build_finance_skill_catalog() -> str:
    """Build the compact Finance catalog shown before skill selection."""

    entries = []
    for skill in FINANCE_SKILLS:
        description = _routing_description(read_finance_skill_body(skill.name))
        entries.append(f"- `{skill.name}` — **{skill.title}**: {description}")
    return "\n".join(entries)


def load_operations_skill_bodies(skill_names: list[str]) -> dict[str, str]:
    """Load selected bodies, adding SQL safety when sql_query is assigned."""

    bodies = {name: render_config_template(read_skill_body(name)) for name in skill_names}
    if "sql_query" in bodies:
        bodies["sql_safety"] = render_config_template(
            (SKILL_ROOT / "common" / "sql_safety.md")
            .read_text(encoding="utf-8")
            .strip()
        )
    return bodies


def load_finance_skill_bodies(skill_names: list[str]) -> dict[str, str]:
    """Load selected Finance bodies, adding SQL safety when sql_query is assigned."""

    bodies = {
        name: render_config_template(read_finance_skill_body(name))
        for name in skill_names
    }
    if "sql_query" in bodies:
        bodies["sql_safety"] = render_config_template(
            (SKILL_ROOT / "common" / "sql_safety.md")
            .read_text(encoding="utf-8")
            .strip()
        )
    return bodies


__all__ = [
    "AgentRuntimeConfig",
    "FINANCE_DEDICATED_SKILL_NAMES",
    "FINANCE_SKILLS",
    "FINANCE_SKILL_BY_NAME",
    "FinanceSkillConfig",
    "FinanceWorkflowConfig",
    "GraphRuntimeConfig",
    "OPERATIONS_DEDICATED_SKILL_NAMES",
    "OPERATIONS_SKILLS",
    "OPERATIONS_SKILL_BY_NAME",
    "OperationsSkillConfig",
    "OperationsWorkflowConfig",
    "SkillDefinition",
    "SkillConfigError",
    "WorkflowConfigError",
    "build_finance_skill_catalog",
    "build_operations_skill_catalog",
    "load_agent_runtime_config",
    "load_finance_skill_bodies",
    "load_finance_skill_config",
    "load_finance_workflow_config",
    "load_operations_skill_bodies",
    "load_operations_skill_config",
    "load_operations_workflow_config",
    "read_skill_body",
    "read_finance_skill_body",
]
