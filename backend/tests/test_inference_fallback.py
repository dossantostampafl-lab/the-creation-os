from __future__ import annotations

import asyncio

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
async def test_interactive_attempt_deadline_advances_to_the_fallback() -> None:
    class SlowPrimary(StubProvider):
        async def generate(self, request: InferenceRequest) -> InferenceResponse:
            self.requests.append(request)
            await asyncio.sleep(0.05)
            return InferenceResponse(provider=self.name, model="auto", content="late")

    primary = SlowPrimary("freellmapi")
    fallback = StubProvider("anthropic")
    bounded_request = request().model_copy(
        update={"metadata": {"attempt_timeout_seconds": 0.01}}
    )

    response = await router_with(primary, fallback).generate(bounded_request)

    assert response.provider == "anthropic"
    assert len(primary.requests) == 1
    assert len(fallback.requests) == 1


@pytest.mark.asyncio
async def test_a_refused_credential_falls_back_when_a_reserve_exists() -> None:
    failure = InferenceAuthenticationError("freellmapi", "FreeLLMAPI authentication failed")
    primary, fallback = StubProvider("freellmapi", failure=failure), StubProvider("anthropic")

    response = await router_with(primary, fallback).generate(request())

    assert response.provider == "anthropic"
    assert len(primary.requests) == 1  # the primary was tried first, and the answer says who served it


@pytest.mark.asyncio
async def test_a_refused_credential_still_surfaces_when_nothing_else_can_answer() -> None:
    failure = InferenceAuthenticationError("freellmapi", "FreeLLMAPI authentication failed")
    fallback_failure = InferenceAuthenticationError("anthropic", "Anthropic authentication failed")
    primary = StubProvider("freellmapi", failure=failure)
    fallback = StubProvider("anthropic", failure=fallback_failure)

    with pytest.raises(InferenceAuthenticationError, match="Anthropic"):
        await router_with(primary, fallback).generate(request())


@pytest.mark.asyncio
async def test_a_refused_credential_is_logged_loudly_without_the_secret(capsys) -> None:
    from loguru import logger

    messages: list[str] = []
    handler = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    try:
        failure = InferenceAuthenticationError("freellmapi", "bad key freellmapi-SECRET")
        await router_with(StubProvider("freellmapi", failure=failure), StubProvider("anthropic")).generate(request())
    finally:
        logger.remove(handler)
    joined = "\n".join(messages)
    assert "refused its credential" in joined and "freellmapi" in joined
    assert "freellmapi-SECRET" not in joined


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


def test_bootstrap_skips_a_fallback_without_its_credentials(freellmapi_with_anthropic_fallback) -> None:
    # A reserve missing its key must not take down a primary that works; it is skipped and logged.
    freellmapi_with_anthropic_fallback.setenv("ANTHROPIC_API_KEY", "")

    router = build_model_router()
    assert tuple(router.registry.names()) == ("freellmapi",)
    assert router._candidate_names(request()) == ["freellmapi"]


@pytest.mark.asyncio
async def test_chatgpt_plan_failure_never_silently_switches_billing_path() -> None:
    primary = StubProvider(
        "chatgpt",
        failure=InferenceRateLimitError(
            "chatgpt",
            "plan limit",
            upstream_status=429,
            upstream_code="subscription_sharing_usage_limit_exceeded",
        ),
    )
    fallback = StubProvider("freellmapi")
    router = router_with(primary, fallback)
    plan_request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="auto",
        requirements=ModelRequirements(preferred_provider="chatgpt"),
    )

    with pytest.raises(InferenceRateLimitError):
        await router.generate(plan_request)

    assert len(primary.requests) == 1
    assert fallback.requests == []


def _plan_request(**metadata) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="auto",
        requirements=ModelRequirements(preferred_provider="chatgpt"),
        metadata=metadata,
    )


def _disclosed_router(primary: StubProvider, fallback: StubProvider) -> ModelRouter:
    registry = ProviderRegistry()
    for provider, model in ((primary, "gpt-plan"), (fallback, "auto")):
        registry.register(provider)
        registry.register_model_profile(ProviderModelProfile(provider=provider.name, model=model, is_default=True))
    return ModelRouter(
        registry,
        fallback_providers=[fallback.name],
        disclosed_fallback_after=["chatgpt"],
    )


@pytest.mark.asyncio
async def test_opted_in_chatgpt_fallback_answers_and_says_why() -> None:
    primary = StubProvider(
        "chatgpt",
        failure=InferenceRateLimitError(
            "chatgpt",
            "plan limit",
            upstream_status=429,
            upstream_code="subscription_sharing_usage_limit_exceeded",
        ),
    )
    fallback = StubProvider("freellmapi")
    router = _disclosed_router(primary, fallback)

    response = await router.generate(_plan_request())

    assert response.provider == "freellmapi"
    assert response.metadata["fallback_from"] == "chatgpt"
    assert response.metadata["fallback_reason"] == "subscription_sharing_usage_limit_exceeded"
    assert router.allows_fallback_after("chatgpt")

    # The usage-limit cooldown pauses plan requests: the next one goes straight to the reserve.
    again = await router.generate(_plan_request())
    assert again.provider == "freellmapi"
    assert len(primary.requests) == 1


@pytest.mark.asyncio
async def test_a_healthy_chatgpt_answer_carries_no_fallback_marker() -> None:
    router = _disclosed_router(StubProvider("chatgpt"), StubProvider("freellmapi"))

    response = await router.generate(_plan_request())

    assert response.provider == "chatgpt"
    assert "fallback_from" not in response.metadata


def test_without_the_opt_in_chatgpt_still_stops() -> None:
    registry = ProviderRegistry()
    assert not ModelRouter(registry).allows_fallback_after("chatgpt")
    assert ModelRouter(registry).allows_fallback_after("freellmapi")


@pytest.mark.asyncio
async def test_chatgpt_gets_its_own_attempt_deadline() -> None:
    class Slow(StubProvider):
        async def generate(self, request: InferenceRequest) -> InferenceResponse:
            await asyncio.sleep(0.05)
            return await super().generate(request)

    router = _disclosed_router(Slow("chatgpt"), StubProvider("freellmapi"))

    # The generic 10ms budget would cut ChatGPT off; its own 1s budget lets it finish.
    response = await router.generate(
        _plan_request(
            attempt_timeout_seconds=0.01,
            attempt_timeout_seconds_by_provider={"chatgpt": 1.0},
        )
    )
    assert response.provider == "chatgpt"

    cut = await router.generate(_plan_request(attempt_timeout_seconds=0.01))
    assert cut.provider == "freellmapi"
    assert cut.metadata["fallback_reason"] == "INFERENCE_TIMEOUT"


def test_bootstrap_opts_chatgpt_into_the_disclosed_fallback_only_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "chatgpt")
    monkeypatch.setattr(settings, "llm_fallback_providers", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://localhost:3001/v1")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto")

    monkeypatch.setattr(settings, "chatgpt_fallback_enabled", False)
    assert not build_model_router().allows_fallback_after("chatgpt")

    monkeypatch.setattr(settings, "chatgpt_fallback_enabled", True)
    router = build_model_router()
    assert tuple(router.registry.names()) == ("chatgpt", "freellmapi")
    assert router.allows_fallback_after("chatgpt")
