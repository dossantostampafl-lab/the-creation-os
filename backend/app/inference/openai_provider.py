from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.inference.contracts import InferenceRequest, InferenceResponse, ProviderHealth, ProviderUnavailable


class OpenAIResponsesProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/models/{self.default_model}",
                    headers=self._headers(),
                )
                if response.status_code >= 400:
                    return ProviderHealth(
                        provider=self.name,
                        available=False,
                        detail=f"model health returned HTTP {response.status_code}",
                    )
        except httpx.HTTPError as exc:
            return ProviderHealth(provider=self.name, available=False, detail=exc.__class__.__name__)
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "input": request.messages,
        }
        if request.requirements.max_output_tokens is not None:
            payload["max_output_tokens"] = request.requirements.max_output_tokens
        if request.metadata.get("enable_capability_intents"):
            payload["tools"] = [self._capability_tool()]

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(self.name, f"OpenAI request failed: {exc.__class__.__name__}") from exc

        if response.status_code >= 400:
            detail = self._safe_error(response)
            raise ProviderUnavailable(self.name, f"OpenAI returned HTTP {response.status_code}: {detail}")

        data = response.json()
        content, metadata = self._normalize_output(data)
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        normalized_usage = {
            key: int(value)
            for key, value in usage.items()
            if isinstance(value, int)
        }
        return InferenceResponse(
            provider=self.name,
            model=str(data.get("model") or request.model or self.default_model),
            content=content,
            finish_reason=str(data.get("status")) if data.get("status") else None,
            usage=normalized_usage,
            metadata=metadata,
        )

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "input": request.messages,
            "stream": True,
        }
        if request.requirements.max_output_tokens is not None:
            payload["max_output_tokens"] = request.requirements.max_output_tokens
        if request.metadata.get("enable_capability_intents"):
            payload["tools"] = [self._capability_tool()]

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/responses",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise ProviderUnavailable(
                            self.name,
                            f"OpenAI stream returned HTTP {response.status_code}: {body[:256]!r}",
                        )
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
                        if event.get("type") == "response.output_text.delta":
                            delta = event.get("delta")
                            if isinstance(delta, str) and delta:
                                yield delta
        except ProviderUnavailable:
            raise
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(self.name, f"OpenAI stream failed: {exc.__class__.__name__}") from exc

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return "provider error"
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("type") or error.get("code") or "provider error")
        return "provider error"

    @staticmethod
    def _normalize_output(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        text_parts: list[str] = []
        metadata: dict[str, Any] = {}
        output = data.get("output")
        if not isinstance(output, list):
            return "", metadata

        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
            elif item_type in {"function_call", "tool_call"} and item.get("name") == "capability_intent":
                arguments = item.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = None
                if isinstance(arguments, dict):
                    metadata["capability_intent"] = arguments
        return "".join(text_parts), metadata

    @staticmethod
    def _capability_tool() -> dict[str, Any]:
        return {
            "type": "function",
            "name": "capability_intent",
            "description": "Request an authorized capability. This only requests execution; policy decides whether it may run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string"},
                    "action": {"type": "string"},
                    "resource": {"type": ["string", "null"]},
                    "arguments": {"type": "object", "additionalProperties": True},
                    "external_effect": {"type": "boolean"},
                    "idempotency_class": {"type": "string", "enum": ["SAFE", "IDEMPOTENT", "AT_MOST_ONCE"]},
                    "idempotency_key": {"type": ["string", "null"]},
                },
                "required": ["capability", "action", "arguments", "external_effect", "idempotency_class"],
                "additionalProperties": False,
            },
        }
