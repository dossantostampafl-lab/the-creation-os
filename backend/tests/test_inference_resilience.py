from __future__ import annotations

import pytest

from app.inference.contracts import (
    CostTier,
    InferenceAuthenticationError,
    InferenceBudgetError,
    InferenceConfigurationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceTimeoutError,
    ModelRequirements,
    ProviderHealth,
    ProviderModelProfile,
    ProviderUnavailable,
)
from app.inference.health import CircuitState, ProviderCircuitBreaker, ProviderRateLimitCooldown
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


class StubProvider:
    def __init__(self, name: str, *, failure: Exception | None = None) -> None:
        self.name = name
        self.failure = failure
        self.calls = 0
        self.health_calls = 0

    async def health(self) -> ProviderHealth:
        self.health_calls += 1
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return InferenceResponse(provider=self.name, model=request.model or "default", content="ok")


def request_for(provider: str, *, max_cost_tier: CostTier) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="model-a",
        requirements=ModelRequirements(
            preferred_provider=provider,
            max_cost_tier=max_cost_tier,
        ),
    )


def register_profile(registry: ProviderRegistry, provider: str, *, cost_tier: CostTier = CostTier.LOW) -> None:
    registry.register_model_profile(
        ProviderModelProfile(
            provider=provider,
            model="model-a",
            capabilities=frozenset({"text"}),
            cost_tier=cost_tier,
        )
    )


@pytest.mark.asyncio
async def test_budget_admits_profile_at_or_below_ceiling() -> None:
    registry = ProviderRegistry()
    provider = StubProvider("cheap")
    registry.register(provider)
    register_profile(registry, "cheap")

    response = await ModelRouter(registry).generate(request_for("cheap", max_cost_tier=CostTier.LOW))

    assert response.provider == "cheap"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_budget_rejects_profile_above_ceiling_before_network_execution() -> None:
    registry = ProviderRegistry()
    provider = StubProvider("premium")
    registry.register(provider)
    register_profile(registry, "premium", cost_tier=CostTier.PREMIUM)

    with pytest.raises(ProviderUnavailable, match="budget"):
        await ModelRouter(registry).generate(request_for("premium", max_cost_tier=CostTier.LOW))

    assert provider.calls == 0


@pytest.mark.asyncio
async def test_budget_rejects_unknown_cost_evidence_when_ceiling_is_explicit() -> None:
    registry = ProviderRegistry()
    provider = StubProvider("unknown")
    registry.register(provider)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="unknown",
            model="model-a",
            capabilities=frozenset({"text"}),
        )
    )

    with pytest.raises(ProviderUnavailable, match="cost evidence unavailable"):
        await ModelRouter(registry).generate(request_for("unknown", max_cost_tier=CostTier.LOW))

    assert provider.calls == 0


def test_circuit_breaker_transitions_closed_open_half_open_closed() -> None:
    breaker = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=10.0)

    assert breaker.state("primary") is CircuitState.CLOSED
    assert breaker.can_attempt("primary", now=0.0) is True

    breaker.record_transient_failure("primary", now=0.0)
    assert breaker.state("primary") is CircuitState.CLOSED

    breaker.record_transient_failure("primary", now=1.0)
    assert breaker.state("primary") is CircuitState.OPEN
    assert breaker.can_attempt("primary", now=10.9) is False

    assert breaker.can_attempt("primary", now=11.0) is True
    assert breaker.state("primary") is CircuitState.HALF_OPEN

    breaker.record_success("primary")
    assert breaker.state("primary") is CircuitState.CLOSED
    assert breaker.can_attempt("primary", now=11.1) is True


def test_circuit_breaker_half_open_failure_reopens() -> None:
    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=5.0)

    breaker.record_transient_failure("primary", now=2.0)
    assert breaker.state("primary") is CircuitState.OPEN
    assert breaker.can_attempt("primary", now=7.0) is True
    assert breaker.state("primary") is CircuitState.HALF_OPEN

    breaker.record_transient_failure("primary", now=7.0)
    assert breaker.state("primary") is CircuitState.OPEN
    assert breaker.can_attempt("primary", now=11.9) is False
    assert breaker.can_attempt("primary", now=12.0) is True


def test_rate_limit_cooldown_blocks_provider_until_expiry() -> None:
    cooldown = ProviderRateLimitCooldown()

    cooldown.register("primary", now=10.0, retry_after_seconds=30.0)

    assert cooldown.can_attempt("primary", now=39.9) is False
    assert cooldown.can_attempt("primary", now=40.0) is True


def test_rate_limit_cooldown_is_scoped_per_provider() -> None:
    cooldown = ProviderRateLimitCooldown()

    cooldown.register("primary", now=5.0, retry_after_seconds=20.0)

    assert cooldown.can_attempt("primary", now=6.0) is False
    assert cooldown.can_attempt("fallback", now=6.0) is True


@pytest.mark.asyncio
async def test_rate_limit_error_falls_back_only_to_explicit_candidate() -> None:
    registry = ProviderRegistry()
    primary = StubProvider("primary", failure=InferenceRateLimitError("primary", "rate limited"))
    fallback = StubProvider("fallback")
    unrelated = StubProvider("unrelated")
    for provider in (primary, fallback, unrelated):
        registry.register(provider)
        register_profile(registry, provider.name)

    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="model-a",
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            max_cost_tier=CostTier.LOW,
        ),
    )
    cooldown = ProviderRateLimitCooldown()
    response = await ModelRouter(
        registry,
        rate_limit_cooldown=cooldown,
        rate_limit_cooldown_seconds=30.0,
        clock=lambda: 100.0,
    ).generate(request)

    assert response.provider == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert unrelated.calls == 0
    assert cooldown.can_attempt("primary", now=129.9) is False


@pytest.mark.asyncio
async def test_timeout_error_falls_back_and_opens_circuit_at_threshold() -> None:
    registry = ProviderRegistry()
    primary = StubProvider("primary", failure=InferenceTimeoutError("primary", "timeout"))
    fallback = StubProvider("fallback")
    for provider in (primary, fallback):
        registry.register(provider)
        register_profile(registry, provider.name)

    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="model-a",
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            max_cost_tier=CostTier.LOW,
        ),
    )
    response = await ModelRouter(registry, circuit_breaker=breaker, clock=lambda: 50.0).generate(request)

    assert response.provider == "fallback"
    assert breaker.state("primary") is CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_circuit_skips_provider_before_health_or_generation() -> None:
    registry = ProviderRegistry()
    primary = StubProvider("primary")
    fallback = StubProvider("fallback")
    for provider in (primary, fallback):
        registry.register(provider)
        register_profile(registry, provider.name)

    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    breaker.record_transient_failure("primary", now=10.0)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="model-a",
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            max_cost_tier=CostTier.LOW,
        ),
    )
    response = await ModelRouter(registry, circuit_breaker=breaker, clock=lambda: 20.0).generate(request)

    assert response.provider == "fallback"
    assert primary.health_calls == 0
    assert primary.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        InferenceAuthenticationError("primary", "bad credentials"),
        InferenceConfigurationError("primary", "bad configuration"),
    ],
)
async def test_auth_and_configuration_errors_fail_closed_without_fallback(error: Exception) -> None:
    registry = ProviderRegistry()
    primary = StubProvider("primary", failure=error)
    fallback = StubProvider("fallback")
    for provider in (primary, fallback):
        registry.register(provider)
        register_profile(registry, provider.name)

    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="model-a",
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            max_cost_tier=CostTier.LOW,
        ),
    )

    with pytest.raises(type(error)):
        await ModelRouter(registry).generate(request)

    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_budget_rejection_fails_closed_without_fallback() -> None:
    registry = ProviderRegistry()
    primary = StubProvider("primary")
    fallback = StubProvider("fallback")
    registry.register(primary)
    registry.register(fallback)
    register_profile(registry, "primary", cost_tier=CostTier.PREMIUM)
    register_profile(registry, "fallback", cost_tier=CostTier.FREE)

    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="model-a",
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            max_cost_tier=CostTier.LOW,
        ),
    )

    with pytest.raises(InferenceBudgetError):
        await ModelRouter(registry).generate(request)

    assert primary.calls == 0
    assert fallback.calls == 0
