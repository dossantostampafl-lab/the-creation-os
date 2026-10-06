from __future__ import annotations

import httpx
import pytest

from app.inference.chatgpt_provider import ChatGPTPlanProvider
from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    ModelRequirements,
)


class DummyCredentials:
    async def access_token(self) -> str:
        return "oauth-access-token"


def provider() -> ChatGPTPlanProvider:
    return ChatGPTPlanProvider(
        credentials=DummyCredentials(),  # type: ignore[arg-type]
        default_model="gpt-6.1-sol",
    )


def test_chatgpt_payload_uses_direct_plan_contract_and_developer_messages() -> None:
    request = InferenceRequest(
        messages=[
            {"role": "system", "content": "system instruction"},
            {"role": "user", "content": "hello"},
        ],
        requirements=ModelRequirements(max_output_tokens=123),
        metadata={"enable_capability_intents": True},
    )

    payload = provider()._payload(request)

    assert payload["model"] == "gpt-6.1-sol"
    assert payload["store"] is False
    assert payload["stream"] is True
    assert payload["input"][0]["role"] == "developer"
    assert "max_output_tokens" not in payload
    assert payload["tools"][0]["type"] == "namespace"
    assert payload["tools"][0]["name"] == "creation"


def test_chatgpt_http_401_is_authentication_failure() -> None:
    response = httpx.Response(
        401,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={"detail": "not authorized"},
    )

    with pytest.raises(InferenceAuthenticationError):
        provider()._raise_http_error(response)


def test_chatgpt_http_429_is_rate_limit_for_router_fallback() -> None:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
    )

    with pytest.raises(InferenceRateLimitError):
        provider()._raise_http_error(response)


def test_chatgpt_stream_usage_limit_maps_to_fallback_signal() -> None:
    event = {
        "type": "response.failed",
        "response": {
            "error": {"code": "subscription_sharing_usage_limit_exceeded"}
        },
    }

    with pytest.raises(InferenceRateLimitError):
        provider()._raise_stream_failure(event)
