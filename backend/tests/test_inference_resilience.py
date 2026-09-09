from __future__ import annotations

import pytest

from app.inference.contracts import (
    CostTier,
    InferenceRequest,
    InferenceResponse,
    ModelRequirements,
    ProviderHealth,
    ProviderModelProfile,
    ProviderUnavailable,
)
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


class StubProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
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


@pytest.mark.asyncio
async def test_budget_admits_profile_at_or_below_ceiling() -> None:
    registry = ProviderRegistry()
    provider = StubProvider("cheap")
    registry.register(provider)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="cheap",
            model="model-a",
            capabilities=frozenset({"text"}),
            cost_tier=CostTier.LOW,
        )
    )

    response = await ModelRouter(registry).generate(
        request_for("cheap", max_cost_tier=CostTier.LOW)
    )

    assert response.provider == "cheap"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_budget_rejects_profile_above_ceiling_before_network_execution() -> None:
    registry = ProviderRegistry()
    provider = StubProvider("premium")
    registry.register(provider)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="premium",
            model="model-a",
            capabilities=frozenset({"text"}),
            cost_tier=CostTier.PREMIUM,
        )
    )

    with pytest.raises(ProviderUnavailable, match="budget"):
        await ModelRouter(registry).generate(
            request_for("premium", max_cost_tier=CostTier.LOW)
        )

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
        await ModelRouter(registry).generate(
            request_for("unknown", max_cost_tier=CostTier.LOW)
        )

    assert provider.calls == 0
