from __future__ import annotations

import json

import httpx
import pytest

from app.ai.embeddings import FreeLLMAPIEmbeddingModel, build_embedding_model
from app.config import settings


@pytest.mark.asyncio
async def test_freellmapi_embedding_serializes_request_and_parses_vector() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    model = FreeLLMAPIEmbeddingModel(
        api_key="embedding-secret",
        model="embedding-model",
        base_url="http://freellmapi.local/v1",
        transport=httpx.MockTransport(handler),
    )

    vector = await model.embed("hello")

    assert seen["url"] == "http://freellmapi.local/v1/embeddings"
    assert seen["authorization"] == "Bearer embedding-secret"
    assert seen["payload"] == {"model": "embedding-model", "input": "hello"}
    assert vector == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_freellmapi_embedding_rejects_malformed_success_without_leaking_secret() -> None:
    secret = "embedding-super-secret"
    model = FreeLLMAPIEmbeddingModel(
        api_key=secret,
        model="embedding-model",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"embedding": "not-a-vector"}]})
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await model.embed("private embedding input")

    message = str(exc_info.value)
    assert secret not in message
    assert "private embedding input" not in message


@pytest.mark.asyncio
async def test_freellmapi_embedding_upstream_failure_is_secret_safe() -> None:
    secret = "embedding-secret-value"
    model = FreeLLMAPIEmbeddingModel(
        api_key=secret,
        model="embedding-model",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, json={"error": f"must not leak {secret}"})
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await model.embed("sensitive text")

    message = str(exc_info.value)
    assert secret not in message
    assert "sensitive text" not in message
    assert "must not leak" not in message


def test_build_embedding_model_requires_freellmapi_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "freellmapi")
    monkeypatch.setattr(settings, "embedding_model", "embedding-model")
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FREELLMAPI_API_KEY"):
        build_embedding_model()


def test_build_embedding_model_creates_freellmapi_model_from_environment(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "freellmapi")
    monkeypatch.setattr(settings, "embedding_model", "embedding-model")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-key")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("FREELLMAPI_TIMEOUT_SECONDS", "17")

    model = build_embedding_model()

    assert isinstance(model, FreeLLMAPIEmbeddingModel)
    assert model.model == "embedding-model"
    assert model.base_url == "http://freellmapi:3001/v1"
    assert model.timeout_seconds == 17.0
