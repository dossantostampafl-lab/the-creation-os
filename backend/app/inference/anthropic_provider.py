from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceTimeoutError,
    InferenceUpstreamResponseError,
    ProviderHealth,
)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    """Claude via the Anthropic Messages API (official SDK)."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        timeout_seconds: float = 120.0,
        max_output_tokens: int = 16000,
        effort: str | None = None,
        refusal_fallback: bool = False,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("Anthropic API key is required")
        if not default_model.strip():
            raise ValueError("Anthropic model is required")
        self._default_model = default_model.strip()
        self._max_output_tokens = max_output_tokens
        self._effort = effort
        self._refusal_fallback = refusal_fallback
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    def _params(self, request: InferenceRequest) -> dict[str, Any]:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                if isinstance(content, str) and content.strip():
                    system_parts.append(content)
                continue
            if role not in {"user", "assistant"} or content in (None, ""):
                continue
            messages.append({"role": role, "content": content})
        if not messages or messages[0]["role"] != "user":
            raise InferenceUpstreamResponseError(self.name, "Anthropic requests must start with a user message")

        params: dict[str, Any] = {
            "model": request.model or self._default_model,
            "max_tokens": request.requirements.max_output_tokens or self._max_output_tokens,
            "messages": messages,
        }
        if system_parts:
            params["system"] = "\n\n".join(system_parts)
        if self._effort is not None:
            params["output_config"] = {"effort": self._effort}
        if self._refusal_fallback:
            params["betas"] = [REFUSAL_FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def _translate(self, exc: anthropic.AnthropicError) -> InferenceError:
        if isinstance(exc, anthropic.APITimeoutError):
            return InferenceTimeoutError(self.name, "Anthropic request timed out")
        if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            return InferenceAuthenticationError(self.name, "Anthropic authentication failed")
        if isinstance(exc, anthropic.RateLimitError):
            return InferenceRateLimitError(self.name, "Anthropic rate limited")
        if isinstance(exc, anthropic.APIStatusError):
            return InferenceUpstreamResponseError(self.name, f"Anthropic returned HTTP {exc.status_code}")
        if isinstance(exc, anthropic.APIConnectionError):
            return InferenceUpstreamResponseError(self.name, "Anthropic connection failed")
        return InferenceUpstreamResponseError(self.name, "Anthropic request failed")

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        params = self._params(request)
        try:
            # Streaming keeps long generations clear of HTTP timeouts; we only need the final message.
            async with self._client.beta.messages.stream(**params) as stream:
                message = await stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise self._translate(exc) from exc

        if message.stop_reason == "refusal":
            raise InferenceUpstreamResponseError(self.name, "Anthropic declined the request")
        content = "".join(block.text for block in message.content if block.type == "text")
        usage = {
            key: value
            for key, value in {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }.items()
            if isinstance(value, int)
        }
        return InferenceResponse(
            provider=self.name,
            model=message.model or str(params["model"]),
            content=content,
            finish_reason=message.stop_reason,
            usage=usage,
        )

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        params = self._params(request)
        try:
            async with self._client.beta.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except anthropic.AnthropicError as exc:
            raise self._translate(exc) from exc

    async def health(self) -> ProviderHealth:
        try:
            await self._client.models.retrieve(self._default_model)
        except anthropic.APITimeoutError:
            return ProviderHealth(provider=self.name, available=False, detail="timeout")
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            return ProviderHealth(provider=self.name, available=False, detail="authentication_failed")
        except anthropic.NotFoundError:
            return ProviderHealth(provider=self.name, available=False, detail="model_not_found")
        except anthropic.RateLimitError:
            return ProviderHealth(provider=self.name, available=False, detail="rate_limited")
        except anthropic.APIStatusError as exc:
            return ProviderHealth(provider=self.name, available=False, detail=f"upstream_status_{exc.status_code}")
        except anthropic.APIConnectionError:
            return ProviderHealth(provider=self.name, available=False, detail="network_error")
        return ProviderHealth(provider=self.name, available=True)
