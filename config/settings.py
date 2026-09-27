"""Typed, cached loaders for project-owned configuration and system environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = PROJECT_ROOT / "config"
ENV_PATH = PROJECT_ROOT / ".env"


class SettingsError(ValueError):
    """Raised when a configuration file or environment setting is invalid."""


class FrozenSettings(BaseModel):
    """Strict immutable base for every YAML-backed settings section."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DatabaseSettings(FrozenSettings):
    connect_timeout_seconds: int = Field(gt=0)


class ConversationSettings(FrozenSettings):
    max_context_messages: int = Field(gt=0)


class ApiSettings(FrozenSettings):
    max_session_id_length: int = Field(gt=0)
    max_chat_message_length: int = Field(gt=0)
    max_run_id_length: int = Field(gt=0)
    sse_retry_ms: int = Field(gt=0)


class AuditSettings(FrozenSettings):
    enabled: bool
    max_string_chars: int = Field(gt=0)
    max_key_chars: int = Field(gt=0)
    max_collection_items: int = Field(gt=0)
    max_event_type_chars: int = Field(gt=0)
    max_event_message_chars: int = Field(gt=0)
    max_error_code_chars: int = Field(gt=0)


class FrontendSettings(FrozenSettings):
    dashboard_filter_debounce_ms: int = Field(gt=0)
    copy_feedback_ms: int = Field(gt=0)


class ApplicationSettings(FrozenSettings):
    database: DatabaseSettings
    conversation: ConversationSettings
    api: ApiSettings
    audit: AuditSettings
    frontend: FrontendSettings


class GraphSettings(FrozenSettings):
    recursion_limit: int = Field(gt=0)


class AgentRuntimeSettings(FrozenSettings):
    supervisor: GraphSettings
    specialist: GraphSettings


class PlanningSettings(FrozenSettings):
    max_subtasks_per_request: int = Field(gt=0)
    max_supervisor_knowledge_subtasks: int = Field(ge=0)
    max_delegations_per_specialist: int = Field(gt=0)
    max_subtask_id_length: int = Field(gt=0)
    min_subtask_question_length: int = Field(gt=0)
    max_subtask_question_length: int = Field(gt=0)
    min_skill_name_length: int = Field(gt=0)
    max_skill_name_length: int = Field(gt=0)
    min_status_message_length: int = Field(gt=0)
    max_status_message_length: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_lengths(self) -> "PlanningSettings":
        if self.min_subtask_question_length > self.max_subtask_question_length:
            raise ValueError("subtask question minimum cannot exceed its maximum")
        if self.min_skill_name_length > self.max_skill_name_length:
            raise ValueError("skill-name minimum cannot exceed its maximum")
        if self.min_status_message_length > self.max_status_message_length:
            raise ValueError("status-message minimum cannot exceed its maximum")
        return self


class FinanceSettings(FrozenSettings):
    max_skills_per_task: int = Field(gt=0)
    max_calls_per_metric_per_subtask: int = Field(gt=0)
    max_scope_filter_length: int = Field(gt=0)
    max_payment_method_filter_length: int = Field(gt=0)


class OperationsSettings(FrozenSettings):
    max_skills_per_task: int = Field(gt=0)


class SqlSettings(FrozenSettings):
    max_rows_per_subtask: int = Field(gt=0)
    hard_max_rows_per_subtask: int = Field(gt=0)
    max_result_chars_per_subtask: int = Field(gt=0)
    hard_max_result_chars_per_subtask: int = Field(gt=0)
    statement_timeout_ms: int = Field(gt=0)
    hard_max_statement_timeout_ms: int = Field(gt=0)
    max_attempts_per_subtask: int = Field(gt=0)
    hard_max_attempts_per_subtask: int = Field(gt=0)
    approval_timeout_seconds: int = Field(gt=0)
    min_approval_timeout_seconds: int = Field(gt=0)
    max_approval_timeout_seconds: int = Field(gt=0)
    max_parameters_per_query: int = Field(gt=0)
    min_sql_length: int = Field(gt=0)
    max_sql_length: int = Field(gt=0)
    max_purpose_length: int = Field(gt=0)
    schema_search_min_query_length: int = Field(gt=0)
    schema_search_max_query_length: int = Field(gt=0)
    entity_type_min_length: int = Field(gt=0)
    entity_type_max_length: int = Field(gt=0)
    entity_term_min_length: int = Field(gt=0)
    entity_term_max_length: int = Field(gt=0)
    table_name_max_length: int = Field(gt=0)
    max_string_cell_chars: int = Field(gt=0)
    schema_search_default_top_k: int = Field(gt=0)
    schema_search_max_top_k: int = Field(gt=0)
    entity_resolution_default_limit: int = Field(gt=0)
    entity_resolution_max_limit: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "SqlSettings":
        pairs = (
            (self.max_rows_per_subtask, self.hard_max_rows_per_subtask, "rows"),
            (
                self.max_result_chars_per_subtask,
                self.hard_max_result_chars_per_subtask,
                "result characters",
            ),
            (
                self.statement_timeout_ms,
                self.hard_max_statement_timeout_ms,
                "statement timeout",
            ),
            (
                self.max_attempts_per_subtask,
                self.hard_max_attempts_per_subtask,
                "SQL attempts",
            ),
        )
        for value, maximum, label in pairs:
            if value > maximum:
                raise ValueError(f"Configured {label} exceeds its hard maximum")
        if not (
            self.min_approval_timeout_seconds
            <= self.approval_timeout_seconds
            <= self.max_approval_timeout_seconds
        ):
            raise ValueError("SQL approval timeout is outside its configured bounds")
        if self.min_sql_length > self.max_sql_length:
            raise ValueError("min_sql_length cannot exceed max_sql_length")
        if self.schema_search_min_query_length > self.schema_search_max_query_length:
            raise ValueError("schema search minimum cannot exceed its maximum")
        if self.entity_type_min_length > self.entity_type_max_length:
            raise ValueError("entity type minimum cannot exceed its maximum")
        if self.entity_term_min_length > self.entity_term_max_length:
            raise ValueError("entity term minimum cannot exceed its maximum")
        if self.schema_search_default_top_k > self.schema_search_max_top_k:
            raise ValueError("schema search default cannot exceed its maximum")
        if self.entity_resolution_default_limit > self.entity_resolution_max_limit:
            raise ValueError("entity resolution default cannot exceed its maximum")
        return self


class RetrievalSettings(FrozenSettings):
    min_similarity: float = Field(ge=-1.0, le=1.0)
    default_top_k: int = Field(gt=0)
    max_top_k: int = Field(gt=0)
    min_query_length: int = Field(gt=0)
    max_query_length: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "RetrievalSettings":
        if self.default_top_k > self.max_top_k:
            raise ValueError("default_top_k cannot exceed max_top_k")
        if self.min_query_length > self.max_query_length:
            raise ValueError("minimum query length cannot exceed maximum")
        return self


class ReviewRetrievalSettings(RetrievalSettings):
    max_semantic_calls_per_subtask: int = Field(gt=0)
    max_expansion_calls_per_subtask: int = Field(gt=0)
    expansion_result_limit: int = Field(gt=0)
    default_expansion_rating_threshold: float = Field(ge=1, le=5)
    max_scope_value_length: int = Field(gt=0)
    max_scope_value_length: int = Field(gt=0)


class TicketRetrievalSettings(RetrievalSettings):
    max_calls_per_subtask: int = Field(gt=0)
    max_issue_category_length: int = Field(gt=0)
    max_status_filter_length: int = Field(gt=0)
    max_issue_category_length: int = Field(gt=0)
    max_status_filter_length: int = Field(gt=0)


class ResolutionSettings(FrozenSettings):
    top_k: int = Field(gt=0)
    similarity_thresholds: tuple[float, ...] = Field(min_length=1)
    max_similarity_gap: float = Field(ge=0.0, le=2.0)
    max_query_length: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ResolutionSettings":
        if any(not -1.0 <= value <= 1.0 for value in self.similarity_thresholds):
            raise ValueError("resolution similarity thresholds must be between -1 and 1")
        return self


class RankingSettings(FrozenSettings):
    bottom_rate_result_limit: int = Field(gt=0)
    interaction_result_limit: int = Field(gt=0)
    interaction_minimum_samples: int = Field(gt=0)


class ResponseSettings(FrozenSettings):
    operations_max_evidence_bullets: int = Field(gt=0)


class AgentSettings(FrozenSettings):
    runtime: AgentRuntimeSettings
    planning: PlanningSettings
    finance: FinanceSettings
    operations: OperationsSettings
    sql: SqlSettings
    knowledge_retrieval: RetrievalSettings
    review_retrieval: ReviewRetrievalSettings
    ticket_retrieval: TicketRetrievalSettings
    product_resolution: ResolutionSettings
    campaign_resolution: ResolutionSettings
    rankings: RankingSettings
    responses: ResponseSettings


class DashboardRules(FrozenSettings):
    inventory_alert_limit: int = Field(gt=0)
    oldest_ticket_limit: int = Field(gt=0)
    top_campaign_limit: int = Field(gt=0)
    negative_roi_campaign_limit: int = Field(gt=0)
    product_ranking_limit: int = Field(gt=0)
    product_minimum_reviews: int = Field(gt=0)
    product_minimum_units_for_return_rate: int = Field(gt=0)


class InventorySeverityRules(FrozenSettings):
    critical_stock_ratio: float = Field(ge=0)
    high_stock_ratio: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_ratios(self) -> "InventorySeverityRules":
        if self.critical_stock_ratio > self.high_stock_ratio:
            raise ValueError("critical stock ratio cannot exceed high stock ratio")
        return self


class ProfitDeteriorationRules(FrozenSettings):
    trigger_drop_pct: float = Field(gt=0)
    high_drop_pct: float = Field(gt=0)


class RefundPressureRules(FrozenSettings):
    trigger_growth_pct: float = Field(gt=0)
    trigger_absolute_increase: float = Field(gt=0)
    high_growth_pct: float = Field(gt=0)
    high_absolute_increase: float = Field(gt=0)


class InventoryReplenishmentRules(FrozenSettings):
    trigger_affected_count: int = Field(gt=0)
    trigger_affected_ratio_pct: float = Field(gt=0)
    high_critical_count: int = Field(gt=0)
    high_affected_ratio_pct: float = Field(gt=0)


class CampaignInefficiencyRules(FrozenSettings):
    trigger_negative_count: int = Field(gt=0)
    trigger_negative_ratio_pct: float = Field(gt=0)
    high_negative_count: int = Field(gt=0)
    high_negative_ratio_pct: float = Field(gt=0)


class CustomerExperienceRules(FrozenSettings):
    low_rating_max: int = Field(ge=1, le=5)
    minimum_reviews_per_period: int = Field(gt=0)
    trigger_average_rating_drop: float = Field(gt=0)
    trigger_low_rating_ratio_increase_pp: float = Field(gt=0)
    high_average_rating_drop: float = Field(gt=0)
    high_low_rating_ratio_increase_pp: float = Field(gt=0)


class BusinessRules(FrozenSettings):
    dashboard: DashboardRules
    inventory_severity: InventorySeverityRules
    profit_deterioration: ProfitDeteriorationRules
    refund_pressure: RefundPressureRules
    inventory_replenishment: InventoryReplenishmentRules
    campaign_inefficiency: CampaignInefficiencyRules
    customer_experience: CustomerExperienceRules


class EnvironmentSettings(FrozenSettings):
    database_url: str
    agent_readonly_database_url: str
    dashscope_api_key: str
    dashscope_workspace_id: str
    app_env: str
    log_directory: Path
    log_console_level: str
    log_file_level: str
    log_backup_count: int = Field(gt=0)
    log_rotate_utc: bool
    log_timezone: ZoneInfo

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )


def _load_yaml(filename: str) -> dict[str, Any]:
    path = CONFIG_ROOT / filename
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SettingsError(f"Configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise SettingsError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"Configuration root must be a mapping: {path}")
    return raw


@lru_cache(maxsize=1)
def load_application_settings() -> ApplicationSettings:
    return ApplicationSettings.model_validate(_load_yaml("app.yml"))


@lru_cache(maxsize=1)
def load_agent_settings() -> AgentSettings:
    return AgentSettings.model_validate(_load_yaml("agent.yml"))


@lru_cache(maxsize=1)
def load_business_rules() -> BusinessRules:
    return BusinessRules.model_validate(_load_yaml("business_rules.yml"))


ALLOWED_ENVIRONMENT_KEYS = (
    "DATABASE_URL",
    "AGENT_READONLY_DATABASE_URL",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_WORKSPACE_ID",
    "APP_ENV",
    "LOG_DIRECTORY",
    "LOG_CONSOLE_LEVEL",
    "LOG_FILE_LEVEL",
    "LOG_BACKUP_COUNT",
    "LOG_ROTATE_UTC",
    "LOG_TIMEZONE",
)


def _environment_value(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise SettingsError(
            f"{name} is missing. Every allowed system setting must be listed in .env."
        )
    return value.strip()


def _environment_bool(name: str) -> bool:
    value = _environment_value(name).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise SettingsError(f"{name} must be a boolean")


@lru_cache(maxsize=1)
def load_environment_settings() -> EnvironmentSettings:
    load_dotenv(ENV_PATH)
    raw_directory = _environment_value("LOG_DIRECTORY")
    directory = Path(raw_directory)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    timezone_name = _environment_value("LOG_TIMEZONE")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise SettingsError(f"Unsupported LOG_TIMEZONE: {timezone_name}") from exc
    try:
        backup_count = int(_environment_value("LOG_BACKUP_COUNT"))
    except ValueError as exc:
        raise SettingsError("LOG_BACKUP_COUNT must be an integer") from exc
    return EnvironmentSettings(
        database_url=_environment_value("DATABASE_URL"),
        agent_readonly_database_url=_environment_value(
            "AGENT_READONLY_DATABASE_URL"
        ),
        dashscope_api_key=_environment_value("DASHSCOPE_API_KEY"),
        dashscope_workspace_id=_environment_value("DASHSCOPE_WORKSPACE_ID"),
        app_env=_environment_value("APP_ENV"),
        log_directory=directory.resolve(),
        log_console_level=_environment_value("LOG_CONSOLE_LEVEL").upper(),
        log_file_level=_environment_value("LOG_FILE_LEVEL").upper(),
        log_backup_count=backup_count,
        log_rotate_utc=_environment_bool("LOG_ROTATE_UTC"),
        log_timezone=timezone,
    )


def prompt_template_values() -> dict[str, str]:
    """Return canonical strings injected into prompts and selected skill bodies."""

    settings = load_agent_settings()
    product = settings.product_resolution
    campaign = settings.campaign_resolution
    return {
        "max_subtasks_per_request": str(
            settings.planning.max_subtasks_per_request
        ),
        "max_supervisor_knowledge_subtasks": str(
            settings.planning.max_supervisor_knowledge_subtasks
        ),
        "max_delegations_per_specialist": str(
            settings.planning.max_delegations_per_specialist
        ),
        "operations_max_skills_per_task": str(
            settings.operations.max_skills_per_task
        ),
        "finance_max_skills_per_task": str(
            settings.finance.max_skills_per_task
        ),
        "sql_max_attempts": str(settings.sql.max_attempts_per_subtask),
        "product_resolution_max_attempts": str(len(product.similarity_thresholds)),
        "product_resolution_thresholds": ", ".join(
            f"{value:.2f}" for value in product.similarity_thresholds
        ),
        "campaign_resolution_max_attempts": str(len(campaign.similarity_thresholds)),
        "campaign_resolution_thresholds": ", ".join(
            f"{value:.2f}" for value in campaign.similarity_thresholds
        ),
        "review_max_semantic_calls": str(
            settings.review_retrieval.max_semantic_calls_per_subtask
        ),
        "review_max_expansion_calls": str(
            settings.review_retrieval.max_expansion_calls_per_subtask
        ),
        "review_default_rating_threshold": str(
            settings.review_retrieval.default_expansion_rating_threshold
        ).rstrip("0").rstrip("."),
        "ticket_max_calls": str(settings.ticket_retrieval.max_calls_per_subtask),
        "finance_metric_max_calls": str(
            settings.finance.max_calls_per_metric_per_subtask
        ),
        "bottom_rate_result_limit": str(settings.rankings.bottom_rate_result_limit),
        "interaction_result_limit": str(settings.rankings.interaction_result_limit),
        "interaction_minimum_samples": str(
            settings.rankings.interaction_minimum_samples
        ),
        "operations_max_evidence_bullets": str(
            settings.responses.operations_max_evidence_bullets
        ),
    }


def render_config_template(template: str) -> str:
    rendered = template
    for name, value in prompt_template_values().items():
        rendered = rendered.replace("{{" + name + "}}", value)
    return rendered


__all__ = [
    "ALLOWED_ENVIRONMENT_KEYS",
    "AgentSettings",
    "ApplicationSettings",
    "BusinessRules",
    "CONFIG_ROOT",
    "ENV_PATH",
    "EnvironmentSettings",
    "PROJECT_ROOT",
    "SettingsError",
    "load_agent_settings",
    "load_application_settings",
    "load_business_rules",
    "load_environment_settings",
    "prompt_template_values",
    "render_config_template",
]
