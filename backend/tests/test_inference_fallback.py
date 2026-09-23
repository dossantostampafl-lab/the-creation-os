from __future__ import annotations

import pytest

from app.config import settings
from app.inference.anthropic_provider import AnthropicProvider
from app.inference.bootstrap import build_model_router, resolve_configured_model
from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceTimeoutError,
    InferenceUpstreamResponseError,
    ModelRequirements,
    ProviderHealth,
    ProviderModelProfile,
)
from app.inference.freellmapi_provider import FreeLLMAPIProvider
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


class StubProvider:
    def __init__(self, name: str, *, failure: Exception | None = None) -> None:
        self.name = name
        self.failure = failure
        self.requests: list[InferenceRequest] = []

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return InferenceResponse(provider=self.name, model=request.model or f"{self.name}-default", content="ok")


def router_with(primary: StubProvider, fallback: StubProvider) -> ModelRouter:
    registry = ProviderRegistry()
    for provider, model in ((primary, "auto"), (fallback, "claude-model")):
        registry.register(provider)
        registry.register_model_profile(ProviderModelProfile(provider=provider.name, model=model, is_default=True))
    return ModelRouter(registry, fallback_providers=[fallback.name])


def request() -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="auto",
        requirements=ModelRequirements(preferred_provider="freellmapi"),
    )


@pytest.mark.asyncio
async def test_the_primary_serves_every_request_while_it_works() -> None:
    primary, fallback = StubProvider("freellmapi"), StubProvider("anthropic")

    response = await router_with(primary, fallback).generate(request())

    assert response.provider == "freellmapi"
    assert len(primary.requests) == 1 and fallback.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    InferenceUpstreamResponseError("freellmapi", "FreeLLMAPI network request failed"),
    InferenceTimeoutError("freellmapi", "FreeLLMAPI request timed out"),
    InferenceRateLimitError("freellmapi", "FreeLLMAPI rate limit reached"),
])
async def test_the_fallback_answers_only_when_the_primary_is_unavailable(failure: Exception) -> None:
    primary, fallback = StubProvider("freellmapi", failure=failure), StubProvider("anthropic")

    response = await router_with(primary, fallback).generate(request())

    assert response.provider == "anthropic"
    # The fallback does not know FreeLLMAPI's "auto" model, so it serves its own default.
    assert fallback.requests[0].model is None
    assert response.model == "anthropic-default"


@pytest.mark.asyncio
async def test_a_misconfigured_primary_fails_closed_instead_of_hiding_behind_the_fallback() -> None:
    failure = InferenceAuthenticationError("freellmapi", "FreeLLMAPI authentication failed")
    primary, fallback = StubProvider("freellmapi", failure=failure), StubProvider("anthropic")

    with pytest.raises(InferenceAuthenticationError):
        await router_with(primary, fallback).generate(request())

    assert fallback.requests == []


@pytest.mark.asyncio
async def test_when_both_fail_the_last_error_surfaces() -> None:
    primary = StubProvider("freellmapi", failure=InferenceTimeoutError("freellmapi", "timed out"))
    fallback = StubProvider("anthropic", failure=InferenceUpstreamResponseError("anthropic", "down"))

    with pytest.raises(InferenceUpstreamResponseError, match="down"):
        await router_with(primary, fallback).generate(request())


@pytest.mark.asyncio
async def test_an_open_primary_circuit_goes_straight_to_the_fallback() -> None:
    primary = StubProvider("freellmapi", failure=InferenceUpstreamResponseError("freellmapi", "down"))
    fallback = StubProvider("anthropic")
    router = router_with(primary, fallback)

    for _ in range(4):
        await router.generate(request())

    assert len(primary.requests) == 3  # the circuit opened after three failures
    assert len(fallback.requests) == 4


@pytest.fixture
def freellmapi_with_anthropic_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-model")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    return monkeypatch


def test_bootstrap_registers_freellmapi_first_and_anthropic_as_last_resort(freellmapi_with_anthropic_fallback) -> None:
    router = build_model_router()

    assert isinstance(router.registry.get("freellmapi"), FreeLLMAPIProvider)
    assert isinstance(router.registry.get("anthropic"), AnthropicProvider)
    assert router._candidate_names(request()) == ["freellmapi", "anthropic"]
    assert resolve_configured_model(router) == "auto"


def test_routers_built_per_request_share_provider_health(freellmapi_with_anthropic_fallback) -> None:
    first, second = build_model_router(), build_model_router()

    assert first._circuit_breaker is second._circuit_breaker
    assert first._rate_limit_cooldown is second._rate_limit_cooldown


def test_bootstrap_without_a_fallback_uses_only_the_primary(freellmapi_with_anthropic_fallback) -> None:
    freellmapi_with_anthropic_fallback.setattr(settings, "llm_fallback_providers", "")

    router = build_model_router()

    assert router._candidate_names(request()) == ["freellmapi"]


def test_bootstrap_rejects_a_fallback_without_its_credentials(freellmapi_with_anthropic_fallback) -> None:
    freellmapi_with_anthropic_fallback.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_model_router()
