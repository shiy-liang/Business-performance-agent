"""Unit tests for model wrappers without making network requests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from model.config import load_model_config
from model.factory import ChatModel, EmbeddingModel


def test_chat_model_uses_bailian_chat_completions_api() -> None:
    settings = load_model_config().chat_model
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="经营表现稳定。"))]
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    model = ChatModel(settings, client=client)

    with patch("model.factory.logger.model_event") as model_event:
        result = asyncio.run(model.ainvoke("概括本月经营表现"))

    assert result == "经营表现稳定。"
    params = create.await_args.kwargs
    assert params["model"] == "qwen3.8-max"
    assert params["messages"] == [{"role": "user", "content": "概括本月经营表现"}]
    assert "temperature" not in params
    assert [call.kwargs["status"] for call in model_event.call_args_list] == [
        "started",
        "completed",
    ]
    assert all("input" not in call.kwargs for call in model_event.call_args_list)


def test_embedding_model_batches_and_preserves_order() -> None:
    settings = load_model_config().embedding_model
    response = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.0, 1.0]),
            SimpleNamespace(index=0, embedding=[1.0, 0.0]),
        ]
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    model = EmbeddingModel(settings, client=client)

    result = asyncio.run(model.aembed_documents(["收入", "毛利"]))

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    params = create.await_args.kwargs
    assert params["model"] == "qwen3.7-text-embedding"
    assert params["dimensions"] == 1024
    assert params["input"] == ["收入", "毛利"]


def test_bailian_connection_configuration() -> None:
    settings = load_model_config()

    assert settings.provider == "aliyun_bailian"
    assert settings.api_key_env == "DASHSCOPE_API_KEY"
    assert settings.workspace_id_env == "DASHSCOPE_WORKSPACE_ID"
    assert settings.chat_model.fallback_model == "qwen3-max"
    assert settings.chat_model.model == "qwen3.8-max"
    assert settings.chat_model.agent_reasoning_effort == {
        "supervisor_routing": "none",
        "supervisor_synthesis": "low",
        "finance": "low",
        "operations": "low",
    }
    assert settings.embedding_model.batch_size == 20


if __name__ == "__main__":
    print("Running tests in test_model_factory.py...")
    test_chat_model_uses_bailian_chat_completions_api()
    test_embedding_model_batches_and_preserves_order()
    test_bailian_connection_configuration()
