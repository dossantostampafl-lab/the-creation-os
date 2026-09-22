from __future__ import annotations

import json

import httpx
import pytest

from app.inference.anthropic_provider import ANTHROPIC_VERSION, AnthropicProvider
from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceTimeoutError,
    InferenceUpstreamResponseError,
    ModelRequirements,
)


def request(*, model: str | None = None, max_output_tokens: int | None = None) -> InferenceRequest:
    return InferenceRequest(
        messages=[
            {"role": "system", "content": "sovereign-prompt"},
            {"role": "user", "content": "who are you"},
        ],
        model=model,
        requirements=ModelRequirements(max_output_tokens=max_output_tokens),
    )


def provider(handler, **kwargs) -> AnthropicProvider:
    return AnthropicProvider(
        api_key="anthropic-secret",
        default_model="claude-model",
        base_url="https://anthropic.invalid/v1",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_constructor_validates_key_model_url_and_limits() -> None:
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="", default_model="claude-model")
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="k", default_model="")
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="k", default_model="m", base_url="file:///tmp/model")
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="k", default_model="m", timeout_seconds=0)
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="k", default_model="m", max_output_tokens=0)


@pytest.mark.asyncio
async def test_generate_hoists_system_prompt_and_returns_text() -> None:
    seen: dict[str, object] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["api_key"] = req.headers.get("x-api-key")
        seen["version"] = req.headers.get("anthropic-version")
        seen["payload"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-served",
                "content": [{"type": "text", "text": "I am "}, {"type": "text", "text": "DEUS"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 9, "output_tokens": 4},
            },
        )

    response = await provider(handler, max_output_tokens=512).generate(request())

    assert seen["url"] == "https://anthropic.invalid/v1/messages"
    assert seen["api_key"] == "anthropic-secret"
    assert seen["version"] == ANTHROPIC_VERSION
    assert seen["payload"] == {
        "model": "claude-model",
        "messages": [{"role": "user", "content": "who are you"}],
        "max_tokens": 512,
        "system": "sovereign-prompt",
    }
    assert response.provider == "anthropic"
    assert response.model == "claude-served"
    assert response.content == "I am DEUS"
    assert response.finish_reason == "end_turn"
    assert response.usage == {"input_tokens": 9, "output_tokens": 4}


@pytest.mark.asyncio
async def test_generate_honours_request_model_and_token_budget() -> None:
    seen: dict[str, object] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    await provider(handler).generate(request(model="claude-override", max_output_tokens=77))

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "claude-override"
    assert payload["max_tokens"] == 77


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, InferenceAuthenticationError),
        (403, InferenceAuthenticationError),
        (429, InferenceRateLimitError),
        (500, InferenceUpstreamResponseError),
    ],
)
async def test_generate_maps_upstream_failures(status: int, expected: type[Exception]) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"type": "upstream"}})

    with pytest.raises(expected):
        await provider(handler).generate(request())


@pytest.mark.asyncio
async def test_generate_rejects_responses_without_text_content() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "thinking"}]})

    with pytest.raises(InferenceUpstreamResponseError):
        await provider(handler).generate(request())


@pytest.mark.asyncio
async def test_generate_maps_timeouts() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    with pytest.raises(InferenceTimeoutError):
        await provider(handler).generate(request())


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_only() -> None:
    body = "\n".join([
        "event: message_start",
        'data: {"type": "message_start"}',
        "",
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}}',
        "",
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}}',
        "",
        "data: not-json",
        "",
        'data: {"type": "message_stop"}',
        "",
    ])

    async def handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content)["stream"] is True
        return httpx.Response(200, text=body)

    chunks = [chunk async for chunk in provider(handler).stream(request())]

    assert chunks == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_stream_raises_on_mid_stream_error_events() -> None:
    body = "\n".join([
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}}',
        "",
        'data: {"type": "error", "error": {"type": "overloaded_error"}}',
        "",
    ])

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    with pytest.raises(InferenceUpstreamResponseError):
        async for _chunk in provider(handler).stream(request()):
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_detail"),
    [(200, None), (401, "authentication_failed"), (429, "rate_limited"), (500, "upstream_status_500")],
)
async def test_health_reports_upstream_state(status: int, expected_detail: str | None) -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "https://anthropic.invalid/v1/models/claude-model"
        return httpx.Response(status, json={})

    health = await provider(handler).health()

    assert health.provider == "anthropic"
    assert health.available is (status == 200)
    assert health.detail == expected_detail
