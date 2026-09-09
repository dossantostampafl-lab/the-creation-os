from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.inference.contracts import (
    CostTier,
    InferenceRequest,
    InferenceResponse,
    ModelRequirements,
    ProviderBenchmarkEvidence,
    ProviderHealth,
    ProviderModelProfile,
)
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


class RoutingProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
        return InferenceResponse(provider=self.name, model="model-a", content=self.name)


def registry_with(*names: str) -> tuple[ProviderRegistry, dict[str, RoutingProvider]]:
    registry = ProviderRegistry()
    providers: dict[str, RoutingProvider] = {}
    for name in names:
        provider = RoutingProvider(name)
        providers[name] = provider
        registry.register(provider)
        registry.register_model_profile(
            ProviderModelProfile(
                provider=name,
                model="model-a",
                capabilities=frozenset({"text"}),
                cost_tier=CostTier.FREE,
                is_default=True,
            )
        )
    return registry, providers


def add_evidence(registry: ProviderRegistry, provider: str, score: float) -> None:
    registry.register_benchmark_evidence(
        ProviderBenchmarkEvidence(
            provider=provider,
            model="model-a",
            suite_id="suite-a",
            score=score,
            sample_count=100,
            observed_at=datetime.now(UTC),
        )
    )


@pytest.mark.asyncio
async def test_ordered_routing_remains_default_even_with_benchmark_evidence() -> None:
    registry, providers = registry_with("primary", "fallback")
    add_evidence(registry, "primary", 0.20)
    add_evidence(registry, "fallback", 0.95)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
        ),
    )

    response = await ModelRouter(registry).generate(request)

    assert response.provider == "primary"
    assert providers["primary"].calls == 1
    assert providers["fallback"].calls == 0


@pytest.mark.asyncio
async def test_benchmark_routing_reorders_only_authorized_candidates() -> None:
    registry, providers = registry_with("primary", "fallback", "unauthorized")
    add_evidence(registry, "primary", 0.20)
    add_evidence(registry, "fallback", 0.90)
    add_evidence(registry, "unauthorized", 1.00)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            routing_strategy="benchmark",
        ),
    )

    response = await ModelRouter(registry).generate(request)

    assert response.provider == "fallback"
    assert providers["fallback"].calls == 1
    assert providers["primary"].calls == 0
    assert providers["unauthorized"].calls == 0


@pytest.mark.asyncio
async def test_benchmark_routing_preserves_original_order_for_equal_scores() -> None:
    registry, providers = registry_with("primary", "fallback")
    add_evidence(registry, "primary", 0.80)
    add_evidence(registry, "fallback", 0.80)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["fallback"],
            routing_strategy="benchmark",
        ),
    )

    response = await ModelRouter(registry).generate(request)

    assert response.provider == "primary"
    assert providers["primary"].calls == 1
    assert providers["fallback"].calls == 0


@pytest.mark.asyncio
async def test_benchmark_routing_puts_verified_evidence_before_missing_evidence() -> None:
    registry, providers = registry_with("primary", "fallback", "second_missing")
    add_evidence(registry, "fallback", 0.40)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        requirements=ModelRequirements(
            preferred_provider="primary",
            fallback_providers=["second_missing", "fallback"],
            routing_strategy="benchmark",
        ),
    )

    response = await ModelRouter(registry).generate(request)

    assert response.provider == "fallback"
    assert providers["fallback"].calls == 1
    assert providers["primary"].calls == 0
    assert providers["second_missing"].calls == 0
