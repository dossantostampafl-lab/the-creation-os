from __future__ import annotations

import pytest

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
    MissionAuthorization,
)
from app.capabilities.providers import (
    CapabilityProviderMetadata,
    ProviderUnavailable,
    RoutedCapabilityAdapter,
)


class FakeProvider:
    def __init__(
        self,
        *,
        name: str,
        capability: str = "research.search",
        external_effect: bool = False,
        minimum_idempotency_class: IdempotencyClass = IdempotencyClass.SAFE,
        health: str = "healthy",
        cost: float = 0.0,
        latency_ms: float = 0.0,
        success_rate: float = 1.0,
        security_review: str = "approved",
        shadow_enabled: bool = True,
        production_enabled: bool = True,
        fail: bool = False,
    ) -> None:
        self.provider_name = name
        self.capability = capability
        self.actions = frozenset({"search"})
        self.external_effect = external_effect
        self.minimum_idempotency_class = minimum_idempotency_class
        self.metadata = CapabilityProviderMetadata(
            origin=f"test:{name}",
            license="test",
            security_review=security_review,
            health=health,
            cost=cost,
            latency_ms=latency_ms,
            success_rate=success_rate,
            shadow_enabled=shadow_enabled,
            production_enabled=production_enabled,
        )
        self.fail = fail
        self.calls = 0

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        self.calls += 1
        if self.fail:
            raise ProviderUnavailable(self.provider_name)
        return CapabilityResult(
            capability=self.capability,
            action=intent.action,
            ok=True,
            data={"served_by": self.provider_name},
        )


def _context(*, external_effects_allowed: bool = False) -> CapabilityContext:
    return CapabilityContext(
        mission_id="mission-1",
        authorization=MissionAuthorization(
            allowed_capabilities=["research.search"],
            external_effects_allowed=external_effects_allowed,
            authorized_by="creator",
            authorized_at="2026-10-03T00:00:00Z",
        ),
    )


@pytest.mark.asyncio
async def test_router_selects_provider_centrally_from_quality_cost_health_and_history_fields() -> None:
    degraded = FakeProvider(name="degraded", health="degraded", success_rate=1.0, cost=0.0)
    healthy_costly = FakeProvider(name="healthy-costly", success_rate=0.95, cost=5.0)
    healthy_best = FakeProvider(name="healthy-best", success_rate=0.99, cost=1.0)
    adapter = RoutedCapabilityAdapter(
        capability="research.search",
        providers=[degraded, healthy_costly, healthy_best],
    )

    result = await adapter.execute(
        CapabilityIntent(capability="research.search", action="search"),
        _context(),
    )

    assert result.ok is True
    assert result.data["provider"] == "healthy-best"
    assert healthy_best.calls == 1
    assert healthy_costly.calls == 0
    assert degraded.calls == 0


@pytest.mark.asyncio
async def test_read_only_provider_failure_can_fail_over_without_changing_authority() -> None:
    first = FakeProvider(name="first", fail=True)
    second = FakeProvider(name="second")
    adapter = RoutedCapabilityAdapter(
        capability="research.search",
        providers=[first, second],
        preferred_providers=["first", "second"],
    )

    result = await adapter.execute(
        CapabilityIntent(capability="research.search", action="search"),
        _context(),
    )

    assert result.ok is True
    assert result.data["provider"] == "second"
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_at_most_once_material_provider_failure_never_fails_over() -> None:
    first = FakeProvider(
        name="first",
        external_effect=True,
        minimum_idempotency_class=IdempotencyClass.AT_MOST_ONCE,
        fail=True,
    )
    second = FakeProvider(
        name="second",
        external_effect=True,
        minimum_idempotency_class=IdempotencyClass.AT_MOST_ONCE,
    )
    adapter = RoutedCapabilityAdapter(
        capability="research.search",
        providers=[first, second],
        preferred_providers=["first", "second"],
    )

    with pytest.raises(ProviderUnavailable):
        await adapter.execute(
            CapabilityIntent(
                capability="research.search",
                action="search",
                idempotency_class=IdempotencyClass.AT_MOST_ONCE,
                idempotency_key="material-1",
            ),
            _context(external_effects_allowed=True),
        )

    assert first.calls == 1
    assert second.calls == 0


def test_router_rejects_providers_that_disagree_on_external_effect_semantics() -> None:
    with pytest.raises(ValueError, match="external-effect semantics"):
        RoutedCapabilityAdapter(
            capability="research.search",
            providers=[
                FakeProvider(name="reader", external_effect=False),
                FakeProvider(name="writer", external_effect=True),
            ],
        )


@pytest.mark.asyncio
async def test_material_provider_must_be_production_enabled_and_certified() -> None:
    pending = FakeProvider(
        name="pending",
        external_effect=True,
        minimum_idempotency_class=IdempotencyClass.AT_MOST_ONCE,
        security_review="pending",
        production_enabled=True,
    )
    adapter = RoutedCapabilityAdapter(capability="research.search", providers=[pending])

    result = await adapter.execute(
        CapabilityIntent(
            capability="research.search",
            action="search",
            idempotency_class=IdempotencyClass.AT_MOST_ONCE,
            idempotency_key="material-1",
        ),
        _context(external_effects_allowed=True),
    )

    assert result.ok is False
    assert result.error["code"] == "NO_ELIGIBLE_PROVIDER"
    assert pending.calls == 0
