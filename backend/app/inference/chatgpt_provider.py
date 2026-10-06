from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.inference.chatgpt_credentials import ChatGPTCredentialStore
from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceUpstreamResponseError,
    ProviderHealth,
    ProviderUnavailable,
)
from app.inference.provider_common import (
    CAPABILITY_INTENT_DESCRIPTION,
    CAPABILITY_INTENT_TOOL,
    capability_intent_parameters,
)


class ChatGPTPlanProvider:
    """Responses API provider authenticated by Sign in with ChatGPT OAuth."""

    name = "chatgpt"

    def __init__(
        self,
        *,
        credentials: ChatGPTCredentialStore,
        default_model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not default_model.strip():
            raise ValueError("CHATGPT_MODEL is required")
        self.credentials = credentials
        self.default_model = default_model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self.credentials.access_token()}",
            "Content-Type": "application/json",
        }

    async def health(self) -> ProviderHealth:
        try:
            headers = await self._headers()
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 10.0)) as client:
                response = await client.get(f"{self.base_url}/models", headers=headers)
        except InferenceAuthenticationError as exc:
            return ProviderHealth(provider=self.name, available=False, detail=str(exc))
        except (ProviderUnavailable, httpx.HTTPError) as exc:
            return ProviderHealth(
                provider=self.name,
                available=False,
                detail=exc.__class__.__name__,
            )
        if response.status_code >= 400:
            return ProviderHealth(
                provider=self.name,
                available=False,
                detail=f"model catalog returned HTTP {response.status_code}",
            )
        return ProviderHealth(provider=self.name, available=True)

    @staticmethod
    def _input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            item = dict(message)
            if item.get("role") == "system":
                item["role"] = "developer"
            normalized.append(item)
        return normalized

    def _payload(self, request: InferenceRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "input": self._input(request.messages),
            "store": False,
            "stream": True,
        }
        if request.metadata.get("enable_capability_intents"):
            payload["tools"] = [
                {
                    "type": "namespace",
                    "name": "creation",
                    "description": "Authorized local Creation OS capabilities.",
                    "tools": [
                        {
                            "type": "function",
                            "name": CAPABILITY_INTENT_TOOL,
                            "description": CAPABILITY_INTENT_DESCRIPTION,
                            "parameters": {
                                **capability_intent_parameters(),
                                "additionalProperties": False,
                            },
                            "strict": True,
                        }
                    ],
                }
            ]
        return payload

    @staticmethod
    def _error_code(payload: Any) -> str:
        if not isinstance(payload, dict):
            return "provider_error"
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("code") or error.get("type") or "provider_error")
        detail = payload.get("detail")
        return str(detail) if detail else "provider_error"

    def _raise_http_error(self, response: httpx.Response) -> None:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        code = self._error_code(payload)
        message = f"ChatGPT returned HTTP {response.status_code}: {code}"
        if response.status_code == 401:
            raise InferenceAuthenticationError(self.name, message)
        if response.status_code == 429:
            raise InferenceRateLimitError(self.name, message)
        if response.status_code in {402, 403}:
            raise ProviderUnavailable(self.name, message)
        if response.status_code >= 500:
            raise ProviderUnavailable(self.name, message)
        raise InferenceUpstreamResponseError(self.name, message)

    @staticmethod
    def _capability_from_output(response_payload: dict[str, Any]) -> dict[str, Any] | None:
        output = response_payload.get("output")
        if not isinstance(output, list):
            return None
        for item in output:
            if not isinstance(item, dict) or item.get("type") not in {"function_call", "tool_call"}:
                continue
            if item.get("name") != CAPABILITY_INTENT_TOOL:
                continue
            arguments = item.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = None
            if isinstance(arguments, dict):
                return arguments
        return None

    def _raise_stream_failure(self, event: dict[str, Any]) -> None:
        response = event.get("response")
        error = response.get("error") if isinstance(response, dict) else None
        code = (
            str(error.get("code") or error.get("type") or "provider_error")
            if isinstance(error, dict)
            else "provider_error"
        )
        if code == "subscription_sharing_usage_limit_exceeded":
            raise InferenceRateLimitError(self.name, code)
        if code in {"subscription_sharing_usage_unavailable", "subscription_sharing_not_enabled"}:
            raise ProviderUnavailable(self.name, code)
        raise InferenceUpstreamResponseError(self.name, code)

    async def _events(self, request: InferenceRequest) -> AsyncIterator[dict[str, Any]]:
        try:
            headers = await self._headers()
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/responses",
                    headers=headers,
                    json=self._payload(request),
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        self._raise_http_error(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line.removeprefix("data: ").strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        event_type = event.get("type")
                        if event_type == "response.failed":
                            self._raise_stream_failure(event)
                        if event_type == "response.incomplete":
                            raise ProviderUnavailable(self.name, "ChatGPT response was incomplete")
                        yield event
        except (
            InferenceAuthenticationError,
            InferenceRateLimitError,
            InferenceUpstreamResponseError,
            ProviderUnavailable,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(self.name, "ChatGPT request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                self.name,
                f"ChatGPT request failed: {exc.__class__.__name__}",
            ) from exc

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        text_parts: list[str] = []
        completed: dict[str, Any] | None = None
        async for event in self._events(request):
            if event.get("type") == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str):
                    text_parts.append(delta)
            elif event.get("type") == "response.completed":
                response = event.get("response")
                if isinstance(response, dict):
                    completed = response
        if completed is None:
            raise ProviderUnavailable(self.name, "ChatGPT stream ended without response.completed")
        metadata: dict[str, Any] = {}
        capability = self._capability_from_output(completed)
        if capability is not None:
            metadata["capability_intent"] = capability
        usage = completed.get("usage") if isinstance(completed.get("usage"), dict) else {}
        normalized_usage = {
            key: int(value)
            for key, value in usage.items()
            if isinstance(value, int)
        }
        return InferenceResponse(
            provider=self.name,
            model=str(completed.get("model") or request.model or self.default_model),
            content="".join(text_parts),
            finish_reason=str(completed.get("status") or "completed"),
            usage=normalized_usage,
            metadata=metadata,
        )

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        completed = False
        async for event in self._events(request):
            event_type = event.get("type")
            if event_type == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    yield delta
            elif event_type == "response.completed":
                completed = True
        if not completed:
            raise ProviderUnavailable(self.name, "ChatGPT stream ended without response.completed")
