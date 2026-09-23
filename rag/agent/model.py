"""LangChain model construction for the Responses API agent runtime."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from model.config import PROJECT_ROOT, load_model_config
from model.factory import ModelEnvironmentError


@lru_cache(maxsize=5)
def create_agent_model(*, reasoning_profile: str | None = None) -> ChatOpenAI:
    """Create a streaming ChatOpenAI client backed by the Responses API."""
    load_dotenv(PROJECT_ROOT / ".env")
    settings = load_model_config()
    api_key = os.getenv(settings.api_key_env, "").strip()
    workspace_id = os.getenv(settings.workspace_id_env, "").strip()
    if not api_key:
        raise ModelEnvironmentError(f"{settings.api_key_env} is not configured")
    if not workspace_id:
        raise ModelEnvironmentError(f"{settings.workspace_id_env} is not configured")

    chat = settings.chat_model
    reasoning_effort = (
        chat.agent_reasoning_effort.get(reasoning_profile, chat.reasoning_effort)
        if reasoning_profile
        else chat.reasoning_effort
    )
    return ChatOpenAI(
        model=chat.model,
        api_key=api_key,
        base_url=settings.base_url.format(workspace_id=workspace_id),
        temperature=chat.temperature,
        max_tokens=chat.max_output_tokens,
        timeout=chat.timeout_seconds,
        max_retries=chat.max_retries,
        streaming=True,
        use_responses_api=True,
        output_version="responses/v1",
        reasoning={"effort": reasoning_effort},
    )


@lru_cache(maxsize=2)
def create_supervisor_model(*, phase: str = "routing") -> ChatOpenAI:
    """Create the model used by the user-facing supervisor."""

    if phase not in {"routing", "synthesis"}:
        raise ValueError(f"Unsupported supervisor phase: {phase}")
    return create_agent_model(reasoning_profile=f"supervisor_{phase}")


@lru_cache(maxsize=2)
def create_specialist_model(agent_name: str) -> ChatOpenAI:
    """Create the model used by Finance and Operations specialists."""

    if agent_name not in {"finance", "operations"}:
        raise ValueError(f"Unsupported specialist: {agent_name}")
    return create_agent_model(reasoning_profile=agent_name)


__all__ = ["create_agent_model", "create_specialist_model", "create_supervisor_model"]
