from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.runtime import CapabilityRuntime
from app.config import settings
from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.models.entities import Creator, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService
from app.services.economy import EconomicPolicyError, ensure_genesis_allocation, project_universe_economy

pytestmark = pytest.mark.integration


class MaterialAdapter:
    name = "material"
    external_effect = True
    minimum_idempotency_class = IdempotencyClass.AT_MOST_ONCE

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        self.calls += 1
        if self.fail:
            raise ConnectionResetError("ambiguous external response")
        return CapabilityResult(capability=self.name, action=intent.action, ok=True, data={"confirmed": True})


async def _authorized_mission(factory) -> tuple[str, str, str]:
    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    actor = Actor(creator_id, "creator")
    cid = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True))
        session.add(Universe(id=universe_id, code=f"u-{universe_id[:8]}", name="Economic Runtime", active=True))
        await session.commit()

    async with factory() as session:
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(actor, "Economic runtime", cid)
        message = await service.add_message(actor, conversation.id, "Execute bounded material action", {}, cid)
        inception = await service.create_inception(actor, conversation.id, message.id, "Material", "Economic action", cid)
        await service.transition_inception(actor, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, cid)
        await service.transition_inception(actor, inception.id, InceptionStatus.APPROVED, cid)
        mission = await service.create_mission(actor, inception.id, "Material mission", "Execute once", cid)
        await service.transition_mission(actor, mission.id, MissionStatus.PLANNED, cid, {
            "strategy": "bounded",
            "steps": [{
                "step_key": "material",
                "title": "Material",
                "description": "Perform one bounded external action",
                "universe": f"u-{universe_id[:8]}",
                "position": 1,
                "depends_on": [],
                "completion_criteria": {"confirmed": True},
            }],
            "completion_criteria": {"confirmed": True},
        })
        await service.transition_mission(actor, mission.id, MissionStatus.VALIDATED, cid)
        await service.create_agent(actor, f"economic-{universe_id[:8]}", "Economic Agent", universe_id, {}, cid)
        await service.transition_mission(actor, mission.id, MissionStatus.AUTHORIZED, cid)
        return creator_id, universe_id, mission.id


def _authorization() -> MissionAuthorization:
    return MissionAuthorization(
        allowed_capabilities=["material"],
        external_effects_allowed=True,
        scope={"actions": {"material": ["purchase"]}},
        authorized_by="creator",
        authorized_at="2026-09-27T00:00:00Z",
    )


def _intent(universe_id: str, key: str) -> CapabilityIntent:
    return CapabilityIntent(
        capability="material",
        action="purchase",
        external_effect=True,
        idempotency_class=IdempotencyClass.AT_MOST_ONCE,
        idempotency_key=key,
        economic={"currency": "BRL", "max_spend": "1.00", "estimated_risk": "1.00", "universe_id": universe_id},
    )


@pytest.mark.asyncio
async def test_material_capability_reserves_before_execution_and_settles_only_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id, universe_id, mission_id = await _authorized_mission(factory)
    monkeypatch.setattr(settings, "real_economic_mode_enabled", True)

    async with factory() as session:
        await ensure_genesis_allocation(
            DomainRepository(session), creator_id=creator_id, universe_id=universe_id, correlation_id=str(uuid.uuid4())
        )

    adapter = MaterialAdapter()
    gateway = CapabilityGateway()
    gateway.register(adapter)
    runtime = CapabilityRuntime(factory, gateway)
    result = await runtime.execute(
        mission_id=mission_id,
        task_id=None,
        agent_execution_id=None,
        intent=_intent(universe_id, "material-success"),
        authorization=_authorization(),
    )
    assert result.ok is True
    assert adapter.calls == 1

    async with factory() as session:
        projection = await project_universe_economy(
            session, creator_id=creator_id, universe_id=universe_id, currency="BRL"
        )
        assert projection.nav == Decimal("10")
        assert projection.reserved == 0
        assert projection.committed == 0
        assert projection.settling == 0
        assert projection.available == Decimal("10")
        assert projection.reconciliation_backlog == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_ambiguous_at_most_once_failure_freezes_capital_and_blocks_equivalent_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id, universe_id, mission_id = await _authorized_mission(factory)
    monkeypatch.setattr(settings, "real_economic_mode_enabled", True)

    async with factory() as session:
        await ensure_genesis_allocation(
            DomainRepository(session), creator_id=creator_id, universe_id=universe_id, correlation_id=str(uuid.uuid4())
        )

    adapter = MaterialAdapter(fail=True)
    gateway = CapabilityGateway()
    gateway.register(adapter)
    runtime = CapabilityRuntime(factory, gateway)
    intent = _intent(universe_id, "material-uncertain")

    with pytest.raises(ConnectionResetError):
        await runtime.execute(
            mission_id=mission_id,
            task_id=None,
            agent_execution_id=None,
            intent=intent,
            authorization=_authorization(),
        )
    assert adapter.calls == 1

    async with factory() as session:
        projection = await project_universe_economy(
            session, creator_id=creator_id, universe_id=universe_id, currency="BRL"
        )
        assert projection.settling == Decimal("1")
        assert projection.reconciliation_backlog == 1
        assert projection.economic_status == "RECONCILIATION_REQUIRED"

    with pytest.raises(EconomicPolicyError, match="RECONCILIATION_REQUIRED"):
        await runtime.execute(
            mission_id=mission_id,
            task_id=None,
            agent_execution_id=None,
            intent=intent,
            authorization=_authorization(),
        )
    assert adapter.calls == 1

    await engine.dispose()
