from __future__ import annotations

import pytest

from app.inference.contracts import CostTier, ProviderHealth, ProviderModelProfile
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.inference.status import build_inference_status


class HealthStubProvider:
    def __init__(self, name: str, *, available: bool, detail: str | None = None) -> None:
        self.name = name
        self._available = available
        self._detail = detail
        self.health_calls = 0

    async def health(self) -> ProviderHealth:
        self.health_calls += 1
        return ProviderHealth(provider=self.name, available=self._available, detail=self._detail)


@pytest.mark.asyncio
async def test_status_snapshot_uses_verified_health_and_registered_model_evidence() -> None:
    registry = ProviderRegistry()
    provider = HealthStubProvider("gateway", available=True)
    registry.register(provider)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="gateway",
            model="model-a",
            capabilities=frozenset({"streaming", "text"}),
            cost_tier=CostTier.LOW,
            is_default=True,
        )
    )

    snapshot = await build_inference_status(ModelRouter(registry))

    assert snapshot.configured is True
    assert snapshot.configured_provider == "gateway"
    assert provider.health_calls == 1
    assert len(snapshot.providers) == 1
    status = snapshot.providers[0]
    assert status.provider == "gateway"
    assert status.available is True
    assert status.detail is None
    assert len(status.models) == 1
    assert status.models[0].model == "model-a"
    assert status.models[0].is_default is True
    assert status.models[0].capabilities == ["streaming", "text"]
    assert status.models[0].cost_tier == "LOW"


@pytest.mark.asyncio
async def test_status_snapshot_preserves_normalized_unavailable_health_only() -> None:
    registry = ProviderRegistry()
    provider = HealthStubProvider("gateway", available=False, detail="upstream_status_503")
    registry.register(provider)

    snapshot = await build_inference_status(ModelRouter(registry))

    assert snapshot.providers[0].available is False
    assert snapshot.providers[0].detail == "upstream_status_503"
