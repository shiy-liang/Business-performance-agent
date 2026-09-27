"""Load non-secret model settings from ``config/model.yml``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "model.yml"


class ModelConfigError(ValueError):
    """Raised when the model configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ChatModelConfig:
    model: str
    fallback_model: str | None
    temperature: float | None
    reasoning_effort: str
    agent_reasoning_effort: dict[str, str]
    max_output_tokens: int
    timeout_seconds: float
    max_retries: int
    retry_initial_seconds: float
    retry_max_seconds: float


@dataclass(frozen=True, slots=True)
class EmbeddingModelConfig:
    model: str
    dimensions: int | None
    batch_size: int
    timeout_seconds: float
    max_retries: int
    retry_initial_seconds: float
    retry_max_seconds: float


@dataclass(frozen=True, slots=True)
class OfflineEmbeddingModelConfig:
    model: str
    dimensions: int
    batch_size: int


@dataclass(frozen=True, slots=True)
class ModelConfig:
    provider: str
    api_key_env: str
    workspace_id_env: str
    base_url: str
    chat_model: ChatModelConfig
    embedding_model: EmbeddingModelConfig
    offline_embedding_model: OfflineEmbeddingModelConfig


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelConfigError(f"{name} must be a mapping in {DEFAULT_CONFIG_PATH}")
    return value


def _positive(value: Any, name: str, *, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ModelConfigError(f"{name} must be a positive integer")
    return value


def _positive_number(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ModelConfigError(f"{name} must be a positive number")
    return float(value)


@lru_cache(maxsize=1)
def load_model_config(path: Path = DEFAULT_CONFIG_PATH) -> ModelConfig:
    """Read and validate the model configuration once per process."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelConfigError(f"Model config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ModelConfigError(f"Invalid YAML in {path}: {exc}") from exc

    root = _mapping(raw, "model config")
    provider = root.get("provider")
    if provider != "aliyun_bailian":
        raise ModelConfigError("provider must currently be 'aliyun_bailian'")

    api_key_env = root.get("api_key_env")
    workspace_id_env = root.get("workspace_id_env")
    base_url = root.get("base_url")
    for value, name in (
        (api_key_env, "api_key_env"),
        (workspace_id_env, "workspace_id_env"),
        (base_url, "base_url"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ModelConfigError(f"{name} must be a non-empty string")
    if "{workspace_id}" not in base_url:
        raise ModelConfigError("base_url must contain the {workspace_id} placeholder")

    chat = _mapping(root.get("chat_model"), "chat_model")
    embedding = _mapping(root.get("embedding_model"), "embedding_model")
    offline_embedding = _mapping(
        root.get("offline_embedding_model"),
        "offline_embedding_model",
    )

    chat_model_name = chat.get("model")
    embedding_model_name = embedding.get("model")
    offline_embedding_model_name = offline_embedding.get("model")
    if not isinstance(chat_model_name, str) or not chat_model_name.strip():
        raise ModelConfigError("chat_model.model must be a non-empty string")
    if not isinstance(embedding_model_name, str) or not embedding_model_name.strip():
        raise ModelConfigError("embedding_model.model must be a non-empty string")
    if not isinstance(offline_embedding_model_name, str) or not offline_embedding_model_name.strip():
        raise ModelConfigError(
            "offline_embedding_model.model must be a non-empty string"
        )

    fallback = chat.get("fallback_model")
    if fallback is not None and (not isinstance(fallback, str) or not fallback.strip()):
        raise ModelConfigError("chat_model.fallback_model must be null or a non-empty string")

    temperature = chat.get("temperature")
    if temperature is not None:
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            raise ModelConfigError("chat_model.temperature must be null or a number")
        if not 0 <= float(temperature) < 2:
            raise ModelConfigError(
                "chat_model.temperature must be between 0 (inclusive) and 2"
            )

    reasoning_effort = chat.get("reasoning_effort")
    supported_reasoning_efforts = {"none", "low", "medium", "xhigh"}
    if reasoning_effort not in supported_reasoning_efforts:
        allowed = ", ".join(sorted(supported_reasoning_efforts))
        raise ModelConfigError(f"chat_model.reasoning_effort must be one of: {allowed}")

    raw_agent_reasoning = chat.get("agent_reasoning_effort")
    if not isinstance(raw_agent_reasoning, dict):
        raise ModelConfigError("chat_model.agent_reasoning_effort must be a mapping")
    supported_agent_profiles = {
        "supervisor_routing",
        "supervisor_synthesis",
        "finance",
        "operations",
    }
    unknown_profiles = sorted(set(raw_agent_reasoning) - supported_agent_profiles)
    if unknown_profiles:
        raise ModelConfigError(
            "chat_model.agent_reasoning_effort contains unsupported profiles: "
            + ", ".join(unknown_profiles)
        )
    agent_reasoning_effort: dict[str, str] = {}
    missing_profiles = sorted(supported_agent_profiles - set(raw_agent_reasoning))
    if missing_profiles:
        raise ModelConfigError(
            "chat_model.agent_reasoning_effort is missing profiles: "
            + ", ".join(missing_profiles)
        )
    for profile in supported_agent_profiles:
        effort = raw_agent_reasoning.get(profile)
        if effort not in supported_reasoning_efforts:
            allowed = ", ".join(sorted(supported_reasoning_efforts))
            raise ModelConfigError(
                f"chat_model.agent_reasoning_effort.{profile} must be one of: {allowed}"
            )
        agent_reasoning_effort[profile] = effort

    chat_timeout = chat.get("timeout_seconds")
    embedding_timeout = embedding.get("timeout_seconds")
    if not isinstance(chat_timeout, (int, float)) or chat_timeout <= 0:
        raise ModelConfigError("chat_model.timeout_seconds must be positive")
    if not isinstance(embedding_timeout, (int, float)) or embedding_timeout <= 0:
        raise ModelConfigError("embedding_model.timeout_seconds must be positive")

    chat_retries = chat.get("max_retries")
    embedding_retries = embedding.get("max_retries")
    if not isinstance(chat_retries, int) or isinstance(chat_retries, bool) or chat_retries < 0:
        raise ModelConfigError("chat_model.max_retries must be a non-negative integer")
    if not isinstance(embedding_retries, int) or isinstance(embedding_retries, bool) or embedding_retries < 0:
        raise ModelConfigError("embedding_model.max_retries must be a non-negative integer")

    return ModelConfig(
        provider=provider,
        api_key_env=api_key_env,
        workspace_id_env=workspace_id_env,
        base_url=base_url,
        chat_model=ChatModelConfig(
            model=chat_model_name,
            fallback_model=fallback,
            temperature=float(temperature) if temperature is not None else None,
            reasoning_effort=reasoning_effort,
            agent_reasoning_effort=agent_reasoning_effort,
            max_output_tokens=_positive(
                chat.get("max_output_tokens"),
                "chat_model.max_output_tokens",
            ),
            timeout_seconds=float(chat_timeout),
            max_retries=chat_retries,
            retry_initial_seconds=_positive_number(
                chat.get("retry_initial_seconds"),
                "chat_model.retry_initial_seconds",
            ),
            retry_max_seconds=_positive_number(
                chat.get("retry_max_seconds"),
                "chat_model.retry_max_seconds",
            ),
        ),
        embedding_model=EmbeddingModelConfig(
            model=embedding_model_name,
            dimensions=_positive(
                embedding.get("dimensions"),
                "embedding_model.dimensions",
                allow_none=True,
            ),
            batch_size=_positive(
                embedding.get("batch_size"),
                "embedding_model.batch_size",
            ),
            timeout_seconds=float(embedding_timeout),
            max_retries=embedding_retries,
            retry_initial_seconds=_positive_number(
                embedding.get("retry_initial_seconds"),
                "embedding_model.retry_initial_seconds",
            ),
            retry_max_seconds=_positive_number(
                embedding.get("retry_max_seconds"),
                "embedding_model.retry_max_seconds",
            ),
        ),
        offline_embedding_model=OfflineEmbeddingModelConfig(
            model=offline_embedding_model_name,
            dimensions=_positive(
                offline_embedding.get("dimensions"),
                "offline_embedding_model.dimensions",
            ),
            batch_size=_positive(
                offline_embedding.get("batch_size"),
                "offline_embedding_model.batch_size",
            ),
        ),
    )
