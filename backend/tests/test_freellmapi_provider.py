from __future__ import annotations

import json

import httpx
import pytest

from app.inference.freellmapi_provider import FreeLLMAPIProvider
from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceTimeoutError,
    InferenceUpstreamResponseError,
    ModelRequirements,
)


@pytest.mark.asyncio
async def test_generate_serializes_chat_request_and_normalizes_response() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "provider/model-a",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "hello from gateway"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            },
        )

    provider = FreeLLMAPIProvider(
        api_key="secret-key",
        default_model="auto:default",
        base_url="http://freellmapi.local/v1",
        transport=httpx.MockTransport(handler),
    )
    response = await provider.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            requirements=ModelRequirements(max_output_tokens=55),
        )
    )

    assert seen["url"] == "http://freellmapi.local/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret-key"
    assert seen["payload"] == {
        "model": "auto:default",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 55,
    }
    assert response.provider == "freellmapi"
    assert response.model == "provider/model-a"
    assert response.content == "hello from gateway"
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}


@pytest.mark.asyncio
async def test_generate_uses_request_model_without_forwarding_arbitrary_metadata() -> None:
    seen_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "chosen-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            },
        )

    provider = FreeLLMAPIProvider(
        api_key="secret-key",
        default_model="default-model",
        base_url="https://gateway.example/v1/",
        transport=httpx.MockTransport(handler),
    )
    await provider.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            model="chosen-model",
            metadata={"api_key": "must-not-forward", "dangerous": {"arbitrary": True}},
        )
    )

    assert seen_payload["model"] == "chosen-model"
    assert "api_key" not in seen_payload
    assert "dangerous" not in seen_payload


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_errors_are_normalized_without_response_body_or_secret(status: int) -> None:
    secret = "super-secret-free-key"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": f"leaked {secret}"}})

    provider = FreeLLMAPIProvider(
        api_key=secret,
        default_model="auto",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(InferenceAuthenticationError) as exc_info:
        await provider.generate(InferenceRequest(messages=[{"role": "user", "content": "private prompt"}]))

    message = str(exc_info.value)
    assert secret not in message
    assert "private prompt" not in message
    assert "leaked" not in message


@pytest.mark.asyncio
async def test_rate_limit_error_is_normalized() -> None:
    provider = FreeLLMAPIProvider(
        api_key="secret",
        default_model="auto",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(429, json={"error": "quota"})),
    )

    with pytest.raises(InferenceRateLimitError):
        await provider.generate(InferenceRequest(messages=[{"role": "user", "content": "hello"}]))


@pytest.mark.asyncio
async def test_timeout_is_normalized_without_prompt_or_secret() -> None:
    secret = "timeout-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timed out", request=request)

    provider = FreeLLMAPIProvider(
        api_key=secret,
        default_model="auto",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(InferenceTimeoutError) as exc_info:
        await provider.generate(InferenceRequest(messages=[{"role": "user", "content": "sensitive"}]))

    assert secret not in str(exc_info.value)
    assert "sensitive" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "internal details"}),
        httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {}}]}),
    ],
)
async def test_upstream_failures_and_malformed_success_are_normalized(response: httpx.Response) -> None:
    provider = FreeLLMAPIProvider(
        api_key="secret",
        default_model="auto",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(lambda _: response),
    )

    with pytest.raises(InferenceUpstreamResponseError):
        await provider.generate(InferenceRequest(messages=[{"role": "user", "content": "hello"}]))


@pytest.mark.asyncio
async def test_health_uses_models_endpoint_without_generation() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    provider = FreeLLMAPIProvider(
        api_key="secret",
        default_model="auto",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(handler),
    )

    health = await provider.health()

    assert health.provider == "freellmapi"
    assert health.available is True
    assert seen == [("GET", "https://gateway.example/v1/models")]


@pytest.mark.asyncio
async def test_stream_yields_only_text_deltas() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"hel"}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"id":"x"}]}}]}',
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            "data: [DONE]",
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    provider = FreeLLMAPIProvider(
        api_key="secret",
        default_model="auto",
        base_url="https://gateway.example/v1",
        transport=httpx.MockTransport(handler),
    )

    chunks = [
        chunk
        async for chunk in provider.stream(
            InferenceRequest(messages=[{"role": "user", "content": "hello"}])
        )
    ]

    assert chunks == ["hel", "lo"]


def test_constructor_rejects_unsafe_or_incomplete_configuration() -> None:
    with pytest.raises(ValueError, match="API key"):
        FreeLLMAPIProvider(api_key="", default_model="auto", base_url="https://gateway.example/v1")
    with pytest.raises(ValueError, match="model"):
        FreeLLMAPIProvider(api_key="key", default_model="", base_url="https://gateway.example/v1")
    with pytest.raises(ValueError, match="http"):
        FreeLLMAPIProvider(api_key="key", default_model="auto", base_url="file:///tmp/gateway")
