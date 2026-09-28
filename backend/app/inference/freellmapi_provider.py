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
from app.inference.provider_common import (
    CAPABILITY_INTENT_DESCRIPTION,
    CAPABILITY_INTENT_TOOL,
    capability_intent_parameters,
    chat_delta_content,
    probe_health,
)


class FreeLLMAPIProvider:
    name = "freellmapi"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not default_model.strip():
            raise ValueError("FreeLLMAPI model is required")
        if timeout_seconds <= 0:
            raise ValueError("FreeLLMAPI timeout must be greater than zero")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("FreeLLMAPI base URL must use http or https")

        # Without a key no Authorization header is sent at all, rather than an empty bearer token.
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._default_model = default_model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
        )

    def _request_payload(self, request: InferenceRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": request.messages,
        }
        if request.requirements.max_output_tokens is not None:
            payload["max_tokens"] = request.requirements.max_output_tokens
        if request.metadata.get("enable_capability_intents"):
            payload["tools"] = [self._capability_tool()]
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _capability_tool() -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": CAPABILITY_INTENT_TOOL,
                "description": CAPABILITY_INTENT_DESCRIPTION,
                "parameters": capability_intent_parameters(),
            },
        }

    @staticmethod
    def _capability_intent(message: dict[str, Any]) -> dict[str, Any] | None:
        """The capability the gateway is being asked for, if the model asked for one."""
        calls = message.get("tool_calls")
        if not isinstance(calls, list):
            return None
        found: dict[str, Any] | None = None
        for call in calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict) or function.get("name") != CAPABILITY_INTENT_TOOL:
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if isinstance(arguments, dict):
                if found is not None:
                    # Only one request is carried onward; two would lose one silently.
                    raise InferenceUpstreamResponseError(
                        "freellmapi", "FreeLLMAPI asked for more than one capability at once"
                    )
                found = arguments
        return found

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
        if not isinstance(message, dict):
            raise InferenceUpstreamResponseError(
                "freellmapi", "FreeLLMAPI returned an invalid response"
            )
        metadata: dict[str, Any] = {}
        intent = FreeLLMAPIProvider._capability_intent(message)
        if intent is not None:
            metadata["capability_intent"] = intent
        content = message.get("content")
        if not isinstance(content, str):
            # A turn that only asks for a capability carries no content, and that is complete.
            if intent is None:
                raise InferenceUpstreamResponseError(
                    "freellmapi", "FreeLLMAPI returned an invalid response"
                )
            message = {**message, "content": ""}

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
            metadata=metadata,
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
                        content = chat_delta_content(payload)
                        if content:
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
        return await probe_health(self._client(), self.name, f"{self._base_url}/models")
