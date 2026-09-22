"""Factories and small async wrappers for shared OpenAI model clients."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from functools import lru_cache
from time import perf_counter
from typing import Any, AsyncIterator, Generic, Sequence, TypeVar

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from model.config import (
    PROJECT_ROOT,
    ChatModelConfig,
    EmbeddingModelConfig,
    load_model_config,
)
from observability import logger

ModelT = TypeVar("ModelT")
RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
API_KEY_PLACEHOLDERS = {
    "",
    "your-openai-api-key",
    "your_openai_api_key_here",
    "replace-with-your-openai-api-key",
    "replace-with-your-dashscope-api-key",
}
WORKSPACE_ID_PLACEHOLDERS = {"", "replace-with-your-bailian-workspace-id"}


class ModelEnvironmentError(RuntimeError):
    """Raised when required model environment variables are unavailable."""


def _api_key() -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    environment_name = load_model_config().api_key_env
    value = os.getenv(environment_name, "").strip()
    if value.lower() in API_KEY_PLACEHOLDERS:
        raise ModelEnvironmentError(
            f"{environment_name} is missing. Replace its placeholder in the project .env file."
        )
    return value


def _base_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    settings = load_model_config()
    workspace_id = os.getenv(settings.workspace_id_env, "").strip()
    if workspace_id.lower() in WORKSPACE_ID_PLACEHOLDERS:
        raise ModelEnvironmentError(
            f"{settings.workspace_id_env} is missing. "
            "Replace its placeholder in the project .env file."
        )
    return settings.base_url.format(workspace_id=workspace_id)


@lru_cache(maxsize=1)
def _shared_client() -> AsyncOpenAI:
    """Create one SDK client per process; Tenacity owns request retries."""

    return AsyncOpenAI(api_key=_api_key(), base_url=_base_url(), max_retries=0)


def _retrying(max_retries: int) -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception_type(RETRYABLE_ERRORS),
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        reraise=True,
    )


def _duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _usage_tokens(response: Any) -> tuple[int | None, int | None]:
    """Read OpenAI-compatible usage fields without assuming they are present."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    input_tokens = getattr(usage, "prompt_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "output_tokens", None)
    return input_tokens, output_tokens


def _error_fields(error: BaseException) -> dict[str, Any]:
    """Return safe diagnostic fields without logging request bodies or credentials."""

    return {
        "error_type": type(error).__name__,
        "error_code": getattr(error, "code", None),
        "status_code": getattr(error, "status_code", None),
    }


class BaseModelFactory(ABC, Generic[ModelT]):
    @abstractmethod
    def create(self) -> ModelT:
        """Create a configured model wrapper."""

    def generator(self) -> ModelT:
        """Keep the reference factory's public construction style."""

        return self.create()


class ChatModel:
    """A minimal async chat interface backed by Chat Completions."""

    def __init__(
        self,
        settings: ChatModelConfig,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> AsyncOpenAI:
        return self._client or _shared_client()

    async def _create_with_retries(self, params: dict[str, Any]) -> Any:
        async for attempt in _retrying(self.settings.max_retries):
            with attempt:
                return await self.client.chat.completions.create(**params)
        raise RuntimeError("Unreachable retry state")

    @staticmethod
    def _messages(
        input: str | list[dict[str, Any]], instructions: str | None
    ) -> list[dict[str, Any]]:
        messages = (
            [{"role": "user", "content": input}]
            if isinstance(input, str)
            else list(input)
        )
        if instructions is not None:
            messages.insert(0, {"role": "system", "content": instructions})
        return messages

    async def create_completion(
        self,
        input: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        model: str | None = None,
        **overrides: Any,
    ) -> Any:
        """Return the complete ChatCompletion for tool calls and metadata."""

        params: dict[str, Any] = {
            "model": model or self.settings.model,
            "messages": self._messages(input, instructions),
            "max_completion_tokens": self.settings.max_output_tokens,
            "timeout": self.settings.timeout_seconds,
        }
        if self.settings.temperature is not None:
            params["temperature"] = self.settings.temperature
        params.update(overrides)

        requested_model = str(params["model"])
        active_model = requested_model
        started_at = perf_counter()
        logger.model_event(
            status="started",
            model=active_model,
            operation="chat.completion",
        )
        try:
            try:
                response = await self._create_with_retries(params)
            except RETRYABLE_ERRORS:
                fallback = self.settings.fallback_model
                if model is not None or not fallback or fallback == params["model"]:
                    raise
                active_model = fallback
                params["model"] = fallback
                response = await self._create_with_retries(params)
        except BaseException as error:
            logger.model_event(
                status="failed",
                model=active_model,
                duration_ms=_duration_ms(started_at),
                operation="chat.completion",
                requested_model=requested_model,
                fallback_used=active_model != requested_model,
                **_error_fields(error),
            )
            raise

        input_tokens, output_tokens = _usage_tokens(response)
        logger.model_event(
            status="completed",
            model=active_model,
            duration_ms=_duration_ms(started_at),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            operation="chat.completion",
            requested_model=requested_model,
            fallback_used=active_model != requested_model,
        )
        return response

    async def ainvoke(
        self,
        input: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        model: str | None = None,
        **overrides: Any,
    ) -> str:
        """Generate text and return the first Chat Completions message."""

        response = await self.create_completion(
            input,
            instructions=instructions,
            model=model,
            **overrides,
        )
        content = response.choices[0].message.content
        return content or ""

    async def astream(
        self,
        input: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        model: str | None = None,
        **overrides: Any,
    ) -> AsyncIterator[Any]:
        """Yield raw Chat Completions chunks for SSE integration."""

        params: dict[str, Any] = {
            "model": model or self.settings.model,
            "messages": self._messages(input, instructions),
            "max_completion_tokens": self.settings.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "timeout": self.settings.timeout_seconds,
        }
        if self.settings.temperature is not None:
            params["temperature"] = self.settings.temperature
        params.update(overrides)
        requested_model = str(params["model"])
        active_model = requested_model
        started_at = perf_counter()
        last_chunk: Any = None
        logger.model_event(
            status="started",
            model=active_model,
            operation="chat.stream",
        )
        try:
            try:
                stream = await self._create_with_retries(params)
            except RETRYABLE_ERRORS:
                fallback = self.settings.fallback_model
                if model is not None or not fallback or fallback == params["model"]:
                    raise
                active_model = fallback
                params["model"] = fallback
                stream = await self._create_with_retries(params)
            async for event in stream:
                last_chunk = event
                yield event
        except BaseException as error:
            logger.model_event(
                status="failed",
                model=active_model,
                duration_ms=_duration_ms(started_at),
                operation="chat.stream",
                requested_model=requested_model,
                fallback_used=active_model != requested_model,
                **_error_fields(error),
            )
            raise

        input_tokens, output_tokens = _usage_tokens(last_chunk)
        logger.model_event(
            status="completed",
            model=active_model,
            duration_ms=_duration_ms(started_at),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            operation="chat.stream",
            requested_model=requested_model,
            fallback_used=active_model != requested_model,
        )


class EmbeddingModel:
    """A batched async embedding interface backed by the Embeddings API."""

    def __init__(
        self,
        settings: EmbeddingModelConfig,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> AsyncOpenAI:
        return self._client or _shared_client()

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed documents in configured batches while preserving input order."""

        values = list(texts)
        if not values:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in values):
            raise ValueError("Embedding inputs must be non-empty strings")

        started_at = perf_counter()
        batch_count = (len(values) + self.settings.batch_size - 1) // self.settings.batch_size
        total_input_tokens = 0
        input_tokens_known = True
        logger.model_event(
            status="started",
            model=self.settings.model,
            operation="embedding",
            item_count=len(values),
            batch_count=batch_count,
        )
        try:
            embeddings: list[list[float]] = []
            for start in range(0, len(values), self.settings.batch_size):
                batch = values[start : start + self.settings.batch_size]
                params: dict[str, Any] = {
                    "model": self.settings.model,
                    "input": batch,
                    "encoding_format": "float",
                    "timeout": self.settings.timeout_seconds,
                }
                if self.settings.dimensions is not None:
                    params["dimensions"] = self.settings.dimensions

                async for attempt in _retrying(self.settings.max_retries):
                    with attempt:
                        response = await self.client.embeddings.create(**params)
                        ordered = sorted(response.data, key=lambda item: item.index)
                        embeddings.extend(item.embedding for item in ordered)
                        input_tokens, _ = _usage_tokens(response)
                        if input_tokens is None:
                            input_tokens_known = False
                        else:
                            total_input_tokens += input_tokens
                        break
        except BaseException as error:
            logger.model_event(
                status="failed",
                model=self.settings.model,
                duration_ms=_duration_ms(started_at),
                operation="embedding",
                item_count=len(values),
                batch_count=batch_count,
                **_error_fields(error),
            )
            raise

        logger.model_event(
            status="completed",
            model=self.settings.model,
            duration_ms=_duration_ms(started_at),
            input_tokens=total_input_tokens if input_tokens_known else None,
            output_tokens=0,
            operation="embedding",
            item_count=len(values),
            batch_count=batch_count,
            dimensions=self.settings.dimensions,
        )
        return embeddings

    async def aembed_query(self, text: str) -> list[float]:
        """Embed one search query."""

        return (await self.aembed_documents([text]))[0]


class ChatModelFactory(BaseModelFactory[ChatModel]):
    def create(self) -> ChatModel:
        return ChatModel(load_model_config().chat_model)


class EmbeddingModelFactory(BaseModelFactory[EmbeddingModel]):
    def create(self) -> EmbeddingModel:
        return EmbeddingModel(load_model_config().embedding_model)


chat_model = ChatModelFactory().generator()
embedding_model = EmbeddingModelFactory().generator()

__all__ = [
    "BaseModelFactory",
    "ChatModel",
    "ChatModelFactory",
    "EmbeddingModel",
    "EmbeddingModelFactory",
    "ModelEnvironmentError",
    "chat_model",
    "embedding_model",
]
