from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceTimeoutError,
    InferenceUpstreamResponseError,
    ProviderHealth,
)


class FreeLLMAPIProvider:
    name = "freellmapi"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("FreeLLMAPI API key is required")
        if not default_model.strip():
            raise ValueError("FreeLLMAPI model is required")
        if timeout_seconds <= 0:
            raise ValueError("FreeLLMAPI timeout must be greater than zero")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("FreeLLMAPI base URL must use http or https")

        self._api_key = api_key
        self._default_model = default_model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def _request_payload(self, request: InferenceRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": request.messages,
        }
        if request.requirements.max_output_tokens is not None:
            payload["max_tokens"] = request.requirements.max_output_tokens
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code in {401, 403}:
            raise InferenceAuthenticationError("freellmapi", "FreeLLMAPI authentication failed")
        if status_code == 429:
            raise InferenceRateLimitError("freellmapi", "FreeLLMAPI rate limit reached")
        if status_code >= 400:
            raise InferenceUpstreamResponseError(
                "freellmapi",
                f"FreeLLMAPI upstream request failed with status {status_code}",
            )

    @staticmethod
    def _parse_response(response: httpx.Response, fallback_model: str) -> InferenceResponse:
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI returned an invalid response"
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI returned an invalid response"
            )
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI returned an invalid response"
            )

        upstream_model = payload.get("model")
        model = upstream_model if isinstance(upstream_model, str) and upstream_model else fallback_model
        finish_reason_value = choices[0].get("finish_reason")
        finish_reason = finish_reason_value if isinstance(finish_reason_value, str) else None

        usage_payload = payload.get("usage")
        usage: dict[str, int] = {}
        if isinstance(usage_payload, dict):
            usage = {
                str(key): value
                for key, value in usage_payload.items()
                if isinstance(value, int) and not isinstance(value, bool)
            }

        return InferenceResponse(
            provider="freellmapi",
            model=model,
            content=message["content"],
            finish_reason=finish_reason,
            usage=usage,
        )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        selected_model = request.model or self._default_model
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=self._request_payload(request),
                )
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError("freellmapi", "FreeLLMAPI request timed out") from exc
        except httpx.HTTPError as exc:
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI network request failed"
            ) from exc

        self._raise_for_status(response.status_code)
        return self._parse_response(response, selected_model)

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=self._request_payload(request, stream=True),
                ) as response:
                    self._raise_for_status(response.status_code)
                    async for line in response.aiter_lines():
                        stripped = line.strip()
                        if not stripped or not stripped.startswith("data:"):
                            continue
                        event = stripped[5:].strip()
                        if event == "[DONE]":
                            break
                        try:
                            payload = json.loads(event)
                        except json.JSONDecodeError as exc:
                            raise InferenceUpstreamResponseError(
                                "freellmapi", "FreeLLMAPI returned invalid streaming data"
                            ) from exc
                        if not isinstance(payload, dict):
                            continue
                        choices = payload.get("choices")
                        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                            continue
                        delta = choices[0].get("delta")
                        if not isinstance(delta, dict):
                            continue
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield content
        except InferenceUpstreamResponseError:
            raise
        except (InferenceAuthenticationError, InferenceRateLimitError):
            raise
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError("freellmapi", "FreeLLMAPI request timed out") from exc
        except httpx.HTTPError as exc:
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI network request failed"
            ) from exc

    async def health(self) -> ProviderHealth:
        try:
            async with self._client() as client:
                response = await client.get(f"{self._base_url}/models")
        except httpx.TimeoutException:
            return ProviderHealth(provider="freellmapi", available=False, detail="timeout")
        except httpx.HTTPError:
            return ProviderHealth(provider="freellmapi", available=False, detail="network_error")

        if 200 <= response.status_code < 300:
            return ProviderHealth(provider="freellmapi", available=True)
        if response.status_code in {401, 403}:
            detail = "authentication_failed"
        elif response.status_code == 429:
            detail = "rate_limited"
        else:
            detail = f"upstream_status_{response.status_code}"
        return ProviderHealth(provider="freellmapi", available=False, detail=detail)
