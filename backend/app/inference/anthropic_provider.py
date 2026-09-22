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

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    """Native Claude Messages API provider."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout_seconds: float = 60.0,
        max_output_tokens: int = 4096,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        normalized_model = default_model.strip()
        if not normalized_key:
            raise ValueError("Anthropic API key is required")
        if not normalized_model:
            raise ValueError("Anthropic model is required")
        if timeout_seconds <= 0:
            raise ValueError("Anthropic timeout must be greater than zero")
        if max_output_tokens <= 0:
            raise ValueError("Anthropic max output tokens must be greater than zero")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Anthropic base URL must use http or https")

        self._api_key = normalized_key
        self._default_model = normalized_model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )

    def _request_payload(self, request: InferenceRequest, *, stream: bool = False) -> dict[str, Any]:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                if isinstance(content, str) and content:
                    system_parts.append(content)
                continue
            messages.append({
                "role": "assistant" if role == "assistant" else "user",
                "content": content,
            })

        payload: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": messages,
            "max_tokens": request.requirements.max_output_tokens or self._max_output_tokens,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if stream:
            payload["stream"] = True
        return payload

    def _raise_for_status(self, status_code: int) -> None:
        if status_code in {401, 403}:
            raise InferenceAuthenticationError(self.name, "Anthropic authentication failed")
        if status_code == 429:
            raise InferenceRateLimitError(self.name, "Anthropic rate limited")
        if status_code >= 400:
            raise InferenceUpstreamResponseError(self.name, "Anthropic returned an upstream error")

    def _parse_response(self, response: httpx.Response, fallback_model: str) -> InferenceResponse:
        try:
            data = response.json()
        except ValueError as exc:
            raise InferenceUpstreamResponseError(self.name, "Anthropic returned malformed JSON") from exc

        if not isinstance(data, dict):
            raise InferenceUpstreamResponseError(self.name, "Anthropic returned an invalid response")
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise InferenceUpstreamResponseError(self.name, "Anthropic returned an invalid response")

        text_parts = [
            block["text"]
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        ]
        if not text_parts:
            raise InferenceUpstreamResponseError(self.name, "Anthropic returned no text content")

        model = data.get("model")
        if not isinstance(model, str) or not model:
            model = fallback_model
        stop_reason = data.get("stop_reason")
        if stop_reason is not None and not isinstance(stop_reason, str):
            stop_reason = None

        usage: dict[str, int] = {}
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = {str(key): value for key, value in raw_usage.items() if isinstance(value, int)}

        return InferenceResponse(
            provider=self.name,
            model=model,
            content="".join(text_parts),
            finish_reason=stop_reason,
            usage=usage,
        )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        payload = self._request_payload(request)
        fallback_model = str(payload["model"])
        try:
            async with self._client() as client:
                response = await client.post(f"{self._base_url}/messages", json=payload)
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError(self.name, "Anthropic request timed out") from exc
        except httpx.HTTPError as exc:
            raise InferenceUpstreamResponseError(self.name, "Anthropic request failed") from exc

        self._raise_for_status(response.status_code)
        return self._parse_response(response, fallback_model)

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        payload = self._request_payload(request, stream=True)
        try:
            async with self._client() as client:
                async with client.stream("POST", f"{self._base_url}/messages", json=payload) as response:
                    self._raise_for_status(response.status_code)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        if event.get("type") == "error":
                            raise InferenceUpstreamResponseError(self.name, "Anthropic stream returned an error")
                        if event.get("type") != "content_block_delta":
                            continue
                        delta = event.get("delta")
                        if not isinstance(delta, dict):
                            continue
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            yield text
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError(self.name, "Anthropic stream timed out") from exc
        except httpx.HTTPError as exc:
            raise InferenceUpstreamResponseError(self.name, "Anthropic stream failed") from exc

    async def health(self) -> ProviderHealth:
        try:
            async with self._client() as client:
                response = await client.get(f"{self._base_url}/models/{self._default_model}")
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
