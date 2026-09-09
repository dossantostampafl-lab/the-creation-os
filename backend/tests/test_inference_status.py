from __future__ import annotations

import pytest

from app.inference.contracts import CostTier, ProviderHealth, ProviderModelProfile
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.inference.status import build_inference_status, configured_inference_status


class HealthStubProvider:
    def __init__(self, name: str, *, available: bool, detail: str | None = None) -> None:
        self.name = name
        self._available = available
        self._detail = detail
        self.health_calls = 0

    async def health(self) -> ProviderHealth:
        self.health_calls += 1
        return ProviderHealth(provider=self.name, available=self._available, detail=self._detail)


def _raise_runtime_error() -> ModelRouter:
    raise RuntimeError("secret-token-must-not-leak")


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


@pytest.mark.asyncio
async def test_configured_status_returns_unconfigured_for_fake_without_building_router() -> None:
    called = False

    def router_factory() -> ModelRouter:
        nonlocal called
        called = True
        raise AssertionError("router must not be built for fake provider")

    snapshot = await configured_inference_status("fake", router_factory=router_factory)

    assert snapshot.configured is False
    assert snapshot.configured_provider == "fake"
    assert snapshot.providers == []
    assert called is False


@pytest.mark.asyncio
async def test_configured_status_redacts_bootstrap_failure_details() -> None:
    snapshot = await configured_inference_status(
        "freellmapi",
        router_factory=_raise_runtime_error,
    )

    assert snapshot.configured is False
    assert snapshot.configured_provider == "freellmapi"
    assert snapshot.providers == []
    assert "secret-token-must-not-leak" not in snapshot.model_dump_json()
