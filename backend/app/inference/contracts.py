from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelRequirements(BaseModel):
    preferred_provider: str | None = None
    fallback_providers: list[str] = Field(default_factory=list)
    requires_streaming: bool = False
    max_output_tokens: int | None = Field(default=None, ge=1)


class InferenceRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(..., min_length=1)
    model: str | None = None
    requirements: ModelRequirements = Field(default_factory=ModelRequirements)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    provider: str
    model: str
    content: str
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider: str
    available: bool
    detail: str | None = None


class InferenceError(RuntimeError):
    code: str = "INFERENCE_ERROR"

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider


class InferenceConfigurationError(InferenceError):
    code: Literal["INFERENCE_CONFIGURATION_ERROR"] = "INFERENCE_CONFIGURATION_ERROR"


class InferenceAuthenticationError(InferenceError):
    code: Literal["INFERENCE_AUTHENTICATION_ERROR"] = "INFERENCE_AUTHENTICATION_ERROR"


class ProviderUnavailable(InferenceError):
    code: Literal["PROVIDER_UNAVAILABLE"] = "PROVIDER_UNAVAILABLE"


class InferenceRateLimitError(ProviderUnavailable):
    code: Literal["INFERENCE_RATE_LIMIT"] = "INFERENCE_RATE_LIMIT"


class InferenceTimeoutError(ProviderUnavailable):
    code: Literal["INFERENCE_TIMEOUT"] = "INFERENCE_TIMEOUT"


class InferenceUpstreamResponseError(ProviderUnavailable):
    code: Literal["INFERENCE_UPSTREAM_RESPONSE_ERROR"] = "INFERENCE_UPSTREAM_RESPONSE_ERROR"
