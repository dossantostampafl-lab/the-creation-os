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


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        default_model: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_name = name.strip()
        normalized_model = default_model.strip()
        if not normalized_name:
            raise ValueError("OpenAI-compatible provider name is required")
        if not normalized_model:
            raise ValueError("OpenAI-compatible model is required")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI-compatible timeout must be greater than zero")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenAI-compatible base URL must use http or https")

        self.name = normalized_name
        self._base_url = base_url.rstrip("/")
        self._default_model = normalized_model
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
            headers=headers,
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

    def _raise_for_status(self, status_code: int) -> None:
        if status_code in {401, 403}:
            raise InferenceAuthenticationError(self.name, "OpenAI-compatible provider authentication failed")
        if status_code == 429:
            raise InferenceRateLimitError(self.name, "OpenAI-compatible provider rate limited")
        if status_code >= 400:
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider returned an upstream error")

    def _parse_response(self, response: httpx.Response, fallback_model: str) -> InferenceResponse:
        try:
            data = response.json()
        except ValueError as exc:
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider returned malformed JSON") from exc

        if not isinstance(data, dict):
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider returned an invalid response")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider returned an invalid response")
        first = choices[0]
        message = first.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider returned an invalid response")

        model = data.get("model")
        if not isinstance(model, str) or not model:
            model = fallback_model
        finish_reason = first.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            finish_reason = None

        usage: dict[str, int] = {}
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = {str(key): value for key, value in raw_usage.items() if isinstance(value, int)}

        return InferenceResponse(
            provider=self.name,
            model=model,
            content=message["content"],
            finish_reason=finish_reason,
            usage=usage,
        )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        payload = self._request_payload(request)
        fallback_model = str(payload["model"])
        try:
            async with self._client() as client:
                response = await client.post(f"{self._base_url}/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError(self.name, "OpenAI-compatible provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider request failed") from exc

        self._raise_for_status(response.status_code)
        return self._parse_response(response, fallback_model)

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        payload = self._request_payload(request, stream=True)
        try:
            async with self._client() as client:
                async with client.stream("POST", f"{self._base_url}/chat/completions", json=payload) as response:
                    self._raise_for_status(response.status_code)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            return
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        choices = event.get("choices")
                        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                            continue
                        delta = choices[0].get("delta")
                        if not isinstance(delta, dict):
                            continue
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield content
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError(self.name, "OpenAI-compatible provider stream timed out") from exc
        except httpx.HTTPError as exc:
            raise InferenceUpstreamResponseError(self.name, "OpenAI-compatible provider stream failed") from exc

    async def health(self) -> ProviderHealth:
        try:
            async with self._client() as client:
                response = await client.get(f"{self._base_url}/models")
        except httpx.TimeoutException:
            return ProviderHealth(provider=self.name, available=False, detail="timeout")
        except httpx.HTTPError:
            return ProviderHealth(provider=self.name, available=False, detail="network_error")

        if response.status_code == 200:
            return ProviderHealth(provider=self.name, available=True)
        if response.status_code in {401, 403}:
            return ProviderHealth(provider=self.name, available=False, detail="authentication_failed")
        if response.status_code == 429:
            return ProviderHealth(provider=self.name, available=False, detail="rate_limited")
        return ProviderHealth(provider=self.name, available=False, detail=f"upstream_status_{response.status_code}")
