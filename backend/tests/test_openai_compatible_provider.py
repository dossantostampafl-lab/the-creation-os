from __future__ import annotations

import json

import httpx
import pytest
from app.inference.openai_compatible_provider import OpenAICompatibleProvider

from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceTimeoutError,
    InferenceUpstreamResponseError,
    ModelRequirements,
)


def request(*, model: str | None = None) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "secret-prompt-marker"}],
        model=model,
        requirements=ModelRequirements(max_output_tokens=42),
        metadata={"api_key": "must-not-forward"},
    )


def test_constructor_validates_name_model_url_and_timeout() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(name="", base_url="http://gateway/v1", default_model="m")
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(name="local", base_url="http://gateway/v1", default_model="")
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(name="local", base_url="file:///tmp/model", default_model="m")
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(name="local", base_url="http://gateway/v1", default_model="m", timeout_seconds=0)


@pytest.mark.asyncio
async def test_generate_uses_openai_compatible_contract_with_optional_auth() -> None:
    seen: dict[str, object] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        seen["authorization"] = req.headers.get("authorization")
        seen["payload"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    provider = OpenAICompatibleProvider(
        name="local_gateway",
        base_url="http://gateway/v1",
        default_model="model-a",
        api_key="gateway-secret",
        transport=httpx.MockTransport(handler),
    )
    response = await provider.generate(request(model="model-b"))

    assert seen["authorization"] == "Bearer gateway-secret"
    assert seen["payload"] == {
        "model": "model-b",
        "messages": [{"role": "user", "content": "secret-prompt-marker"}],
        "max_tokens": 42,
    }
    assert response.provider == "local_gateway"
    assert response.model == "served-model"
    assert response.content == "hello"
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 2}


@pytest.mark.asyncio
async def test_generate_omits_authorization_when_api_key_is_absent() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        assert "authorization" not in req.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        name="ollama",
        base_url="http://ollama:11434/v1",
        default_model="local-model",
        transport=httpx.MockTransport(handler),
    )
    response = await provider.generate(request())
    assert response.model == "local-model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, InferenceAuthenticationError), (403, InferenceAuthenticationError), (429, InferenceRateLimitError), (500, InferenceUpstreamResponseError)],
)
async def test_generate_normalizes_upstream_errors_without_leaking_body_or_secret(status: int, error_type: type[Exception]) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="upstream-secret-body-marker")

    provider = OpenAICompatibleProvider(
        name="gateway",
        base_url="http://gateway/v1",
        default_model="model-a",
        api_key="gateway-secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(error_type) as exc_info:
        await provider.generate(request())

    message = str(exc_info.value)
    assert "gateway-secret" not in message
    assert "secret-prompt-marker" not in message
    assert "upstream-secret-body-marker" not in message


@pytest.mark.asyncio
async def test_generate_normalizes_timeout_and_malformed_response() -> None:
    async def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("raw timeout secret", request=req)

    timeout_provider = OpenAICompatibleProvider(
        name="gateway",
        base_url="http://gateway/v1",
        default_model="model-a",
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(InferenceTimeoutError):
        await timeout_provider.generate(request())

    malformed_provider = OpenAICompatibleProvider(
        name="gateway",
        base_url="http://gateway/v1",
        default_model="model-a",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": []})),
    )
    with pytest.raises(InferenceUpstreamResponseError):
        await malformed_provider.generate(request())


@pytest.mark.asyncio
async def test_stream_yields_only_text_deltas_and_health_probes_models() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/models":
            return httpx.Response(200, json={"data": []})
        assert req.url.path == "/v1/chat/completions"
        body = (
            'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    provider = OpenAICompatibleProvider(
        name="gateway",
        base_url="http://gateway/v1",
        default_model="model-a",
        transport=httpx.MockTransport(handler),
    )
    chunks = [chunk async for chunk in provider.stream(request())]
    health = await provider.health()

    assert chunks == ["hel", "lo"]
    assert health.provider == "gateway"
    assert health.available is True
