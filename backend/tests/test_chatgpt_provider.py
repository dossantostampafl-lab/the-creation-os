from __future__ import annotations

import httpx
import pytest

from app.inference.chatgpt_provider import ChatGPTPlanProvider, listed_model_slugs
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
    tool = payload["tools"][0]["tools"][0]
    assert tool["parameters"]["properties"]["arguments"]["additionalProperties"] is True
    assert tool["strict"] is False
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


def test_chatgpt_structured_invalid_user_is_authentication_failure() -> None:
    response = httpx.Response(
        401,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={"error": {"code": "subscription_sharing_invalid_user"}},
    )

    with pytest.raises(InferenceAuthenticationError):
        provider()._raise_http_error(response)


def test_chatgpt_structured_temporary_usage_error_uses_fallback_signal() -> None:
    response = httpx.Response(
        503,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={"error": {"code": "subscription_sharing_user_unavailable"}},
    )

    from app.inference.contracts import ProviderUnavailable

    with pytest.raises(ProviderUnavailable):
        provider()._raise_http_error(response)


def test_chatgpt_direct_admission_503_preserves_detail_without_inventing_code() -> None:
    from app.inference.contracts import ProviderUnavailable

    response = httpx.Response(
        503,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        headers={"x-request-id": "req_direct_503"},
        json={"detail": "direct route temporarily unavailable"},
    )

    with pytest.raises(ProviderUnavailable) as captured:
        provider()._raise_http_error(response)

    error = captured.value
    assert error.upstream_status == 503
    assert error.upstream_code is None
    assert error.request_id == "req_direct_503"
    assert error.upstream_body == {"detail": "direct route temporarily unavailable"}
    assert "direct route temporarily unavailable" in str(error)


def test_chatgpt_model_catalog_uses_only_exact_list_visibility_and_slug() -> None:
    assert listed_model_slugs(
        {
            "models": [
                {"slug": "gpt-visible-a", "display_name": "A", "visibility": "list"},
                {"slug": "gpt-hidden", "visibility": "hidden"},
                {"id": "legacy-id", "visibility": "list"},
                {"slug": "gpt-visible-b", "visibility": "list"},
            ],
            "data": [{"id": "must-not-be-used"}],
        }
    ) == ["gpt-visible-a", "gpt-visible-b"]


def test_chatgpt_http_error_preserves_status_code_param_and_request_id() -> None:
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        headers={"x-request-id": "req_si_wc_123"},
        json={"error": {"code": "subscription_sharing_unsupported_capability", "param": "temperature"}},
    )

    with pytest.raises(Exception) as captured:
        provider()._raise_http_error(response)

    error = captured.value
    assert getattr(error, "upstream_status") == 400
    assert getattr(error, "upstream_code") == "subscription_sharing_unsupported_capability"
    assert getattr(error, "upstream_param") == "temperature"
    assert getattr(error, "request_id") == "req_si_wc_123"


def test_chatgpt_explicit_stream_error_is_not_ignored() -> None:
    from app.inference.contracts import InferenceUpstreamResponseError

    event = {
        "type": "error",
        "code": "ERR_SOMETHING",
        "message": "Something went wrong",
        "param": "input",
        "sequence_number": 7,
    }

    with pytest.raises(InferenceUpstreamResponseError) as captured:
        provider()._raise_stream_error(event)

    assert captured.value.upstream_code == "ERR_SOMETHING"
    assert captured.value.upstream_param == "input"
    assert captured.value.upstream_body == event
