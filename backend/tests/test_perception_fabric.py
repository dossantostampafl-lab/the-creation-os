from __future__ import annotations

import pytest

from app.autonomy.perception import PerceptionFabric, PerceptionPolicyError, SensorBinding
from app.capabilities.contracts import CapabilityContext, CapabilityIntent, CapabilityResult, IdempotencyClass
from app.capabilities.gateway import CapabilityGateway


class FakeSensorAdapter:
    minimum_idempotency_class = IdempotencyClass.SAFE

    def __init__(self, name: str, *, external_effect: bool = False) -> None:
        self.name = name
        self.external_effect = external_effect
        self.calls: list[CapabilityIntent] = []

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        self.calls.append(intent)
        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=True,
            data={"items": [{"title": "signal", "content": "verified demand gap"}]},
        )


@pytest.mark.asyncio
async def test_universe_priors_bias_attention_but_do_not_grant_sensor_authority() -> None:
    web = FakeSensorAdapter("web")
    hidden = FakeSensorAdapter("research.semantic")
    gateway = CapabilityGateway()
    gateway.register(web)
    gateway.register(hidden)

    fabric = PerceptionFabric(
        gateway,
        bindings={
            "web.search": SensorBinding(capability="web", action="search"),
            "research.semantic": SensorBinding(capability="research.semantic", action="search"),
        },
        allowed_sensors={"web.search"},
    )

    observations = await fabric.observe(
        creator_id="creator-1",
        universe_code="engineering",
        preferred_sensors=["research.semantic", "web.search"],
        query="software latency",
        explore=True,
    )

    assert [item.sensor for item in observations] == ["web.search"]
    assert len(web.calls) == 1
    assert hidden.calls == []


@pytest.mark.asyncio
async def test_pre_mission_perception_refuses_material_sensor_even_if_allowlisted() -> None:
    writer = FakeSensorAdapter("repo.write", external_effect=True)
    gateway = CapabilityGateway()
    gateway.register(writer)
    fabric = PerceptionFabric(
        gateway,
        bindings={"repo.write": SensorBinding(capability="repo.write", action="write")},
        allowed_sensors={"repo.write"},
    )

    with pytest.raises(PerceptionPolicyError, match="external effect"):
        await fabric.observe(
            creator_id="creator-1",
            universe_code="engineering",
            preferred_sensors=["repo.write"],
            query="change repository",
            explore=False,
        )

    assert writer.calls == []


@pytest.mark.asyncio
async def test_cross_sector_exploration_can_use_allowed_nonpreferred_sensor() -> None:
    web = FakeSensorAdapter("web")
    semantic = FakeSensorAdapter("research.semantic")
    gateway = CapabilityGateway()
    gateway.register(web)
    gateway.register(semantic)
    fabric = PerceptionFabric(
        gateway,
        bindings={
            "web.search": SensorBinding(capability="web", action="search"),
            "research.semantic": SensorBinding(capability="research.semantic", action="search"),
        },
        allowed_sensors={"web.search", "research.semantic"},
        max_sensors_per_cycle=4,
    )

    observations = await fabric.observe(
        creator_id="creator-1",
        universe_code="engineering",
        preferred_sensors=["web.search"],
        query="automation opportunity",
        explore=True,
    )

    assert [item.sensor for item in observations] == ["web.search", "research.semantic"]
    assert len(web.calls) == 1
    assert len(semantic.calls) == 1
