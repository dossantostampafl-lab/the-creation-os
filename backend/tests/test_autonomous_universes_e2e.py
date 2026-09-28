from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, CapabilityResult, IdempotencyClass
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.mission_authorization import set_mission_authorization
from app.capabilities.runtime import CapabilityRuntime
from app.config import settings
from app.core.domain import Actor, MissionStatus
from app.inference.contracts import InferenceResponse, ProviderHealth, ProviderModelProfile
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.kernel.agent_runtime import AgentRuntime
from app.models.entities import Agent, Chronicle, Creator, Mission, Task, Universe, UniverseMemory
from app.repositories.domain import DomainRepository
from app.schemas.opportunity import OpportunityThesisCreate
from app.services.domain import LivingCoreService
from app.services.economy import ensure_genesis_allocation, project_universe_economy
from app.services.opportunity import (
    acquire_executive_lease,
    create_mission_from_opportunity,
    create_or_get_opportunity,
    record_learning_episode,
    select_thesis,
    submit_thesis,
)

pytestmark = pytest.mark.integration


class FakeInferenceProvider:
    name = "e2e-fake"

    def __init__(self, *, universe_id: str, opportunity_id: str) -> None:
        self.universe_id = universe_id
        self.opportunity_id = opportunity_id

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request) -> InferenceResponse:
        return InferenceResponse(
            provider=self.name,
            model="e2e-model",
            content="execute the authorized opportunity action",
            metadata={
                "capability_intent": {
                    "capability": "e2e_material",
                    "action": "execute",
                    "resource": "test:external-effect",
                    "arguments": {"value": "confirmed"},
                    "external_effect": True,
                    "idempotency_class": "at_most_once",
                    "idempotency_key": "e2e-material-effect",
                    "economic": {
                        "currency": "BRL",
                        "max_spend": "1.00",
                        "estimated_risk": "1.00",
                        "universe_id": self.universe_id,
                        "opportunity_id": self.opportunity_id,
                    },
                }
            },
        )


class ConfirmedMaterialAdapter:
    name = "e2e_material"
    external_effect = True
    minimum_idempotency_class = IdempotencyClass.AT_MOST_ONCE

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=True,
            data={"confirmed": True, "economic": {"pnl": "0.50"}},
        )


def thesis_payload(creator_id: str, value: str, confidence: float) -> OpportunityThesisCreate:
    return OpportunityThesisCreate(
        creator_id=creator_id,
        proposed_value=value,
        target_payer="operations team",
        capture_path="bounded service",
        estimated_cost={"currency": "BRL", "amount": 1},
        expected_value={"currency": "BRL", "amount": 3},
        max_downside={"currency": "BRL", "amount": 1},
        confidence=confidence,
        falsification_conditions=["payer rejects verified offer"],
        evidence_refs=["test:e2e:evidence"],
    )


@pytest.mark.asyncio
async def test_autonomous_opportunity_economy_runs_through_existing_mission_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    creator_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    critic_universe_id = str(uuid.uuid4())
    creator = Actor(creator_id, "creator")

    async with factory() as session:
        session.add_all([
            Creator(id=creator_id, username=f"creator-{creator_id[:8]}", password_hash="x", is_active=True),
            Universe(id=universe_id, code=f"e2e-{universe_id[:8]}", name="E2E Opportunity", active=True),
            Universe(id=critic_universe_id, code=f"critic-{critic_universe_id[:8]}", name="E2E Critic", active=True),
        ])
        await session.flush()
        session.add(Agent(
            universe_id=universe_id,
            code=f"e2e-agent-{universe_id[:8]}",
            name="E2E Agent",
            active=True,
            capabilities_json={"inference_provider": "e2e-fake"},
        ))
        await session.commit()

    async with factory() as session:
        repo = DomainRepository(session)
        opportunity = await create_or_get_opportunity(
            repo,
            creator_id=creator_id,
            discovered_by_universe_id=universe_id,
            sector="software",
            problem_or_gap="verified operational context gap",
            capture_mechanism="bounded subscription",
            evidence_refs=["test:e2e:evidence"],
            time_window={"kind": "test", "until": "2026-12-31T23:59:59Z"},
            correlation_id=str(uuid.uuid4()),
        )
        primary = await submit_thesis(
            repo,
            opportunity_id=opportunity.id,
            universe_id=universe_id,
            thesis=thesis_payload(creator_id, "automate verified workflow", 0.85),
            correlation_id=str(uuid.uuid4()),
        )
        await submit_thesis(
            repo,
            opportunity_id=opportunity.id,
            universe_id=critic_universe_id,
            thesis=thesis_payload(creator_id, "offer assisted workflow", 0.65),
            correlation_id=str(uuid.uuid4()),
        )
        selected = await select_thesis(
            repo,
            opportunity_id=opportunity.id,
            thesis_id=primary.id,
            correlation_id=str(uuid.uuid4()),
        )
        assert selected.status == "SELECTED"

        lease = await acquire_executive_lease(
            repo,
            opportunity_id=opportunity.id,
            thesis_id=primary.id,
            universe_id=universe_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            correlation_id=str(uuid.uuid4()),
        )
        mission = await create_mission_from_opportunity(
            repo,
            creator_id=creator_id,
            opportunity_id=opportunity.id,
            thesis_id=primary.id,
            executive_lease_id=lease.id,
            title="Opportunity E2E",
            objective="capture bounded verified value",
            authorization={},
            correlation_id=str(uuid.uuid4()),
        )

    universe_code = f"e2e-{universe_id[:8]}"
    correlation_id = str(uuid.uuid4())
    async with factory() as session:
        service = LivingCoreService(DomainRepository(session))
        await service.transition_mission(
            creator,
            mission.id,
            MissionStatus.PLANNED,
            correlation_id,
            {
                "strategy": "existing-runtime-only",
                "steps": [{
                    "step_key": "execute-opportunity",
                    "title": "Execute opportunity",
                    "description": "Use the existing capability runtime",
                    "universe": universe_code,
                    "position": 1,
                    "depends_on": [],
                    "completion_criteria": {"confirmed": True},
                }],
                "completion_criteria": {"confirmed": True},
            },
        )
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, correlation_id)
        await set_mission_authorization(
            service.repo,
            actor=creator,
            mission_id=mission.id,
            authorization={
                "allowed_capabilities": ["e2e_material"],
                "denied_capabilities": [],
                "scope": {"actions": {"e2e_material": ["execute"]}},
                "external_effects_allowed": True,
                "risk_level": "low",
                "budget": {"currency": "BRL", "max_spend": "1.00"},
                "expires_at": None,
                "version": 1,
            },
            correlation_id=correlation_id,
        )
        await service.transition_mission(creator, mission.id, MissionStatus.DISTRIBUTED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.EXECUTING, correlation_id)

    monkeypatch.setattr(settings, "real_economic_mode_enabled", True)
    async with factory() as session:
        await ensure_genesis_allocation(
            DomainRepository(session),
            creator_id=creator_id,
            universe_id=universe_id,
            correlation_id=correlation_id,
        )

    gateway = CapabilityGateway()
    gateway.register(ConfirmedMaterialAdapter())
    capability_runtime = CapabilityRuntime(factory, gateway)

    registry = ProviderRegistry()
    provider = FakeInferenceProvider(universe_id=universe_id, opportunity_id=opportunity.id)
    registry.register(provider)
    registry.register_model_profile(
        ProviderModelProfile(
            provider=provider.name,
            model="e2e-model",
            is_default=True,
        )
    )
    runtime = AgentRuntime(factory, ModelRouter(registry), capability_runtime=capability_runtime)
    assert await runtime.run_next(mission.id, correlation_id) is True

    async with factory() as session:
        task = await session.scalar(select(Task).where(Task.mission_id == mission.id))
        assert task is not None and task.status == "SUCCEEDED"
        service = LivingCoreService(DomainRepository(session))
        manifested = await service.transition_mission(
            creator, mission.id, MissionStatus.MANIFESTED, correlation_id
        )
        assert manifested.status == "manifested"

    async with factory() as session:
        repo = DomainRepository(session)
        memory = await record_learning_episode(
            repo,
            universe_id=universe_id,
            source="e2e-capability-result",
            strategy={"provider": "e2e_material", "sensor": "web.search", "detector": "demand_gap"},
            outcome={"success": True, "reward": 1.0},
            correlation_id=correlation_id,
        )
        assert isinstance(memory, UniverseMemory)

        projection = await project_universe_economy(
            session,
            creator_id=creator_id,
            universe_id=universe_id,
            currency="BRL",
        )
        assert projection.nav == Decimal("10.50")
        assert projection.available == Decimal("10.50")
        assert projection.reconciliation_backlog == 0

        persisted_mission = await session.get(Mission, mission.id)
        assert persisted_mission is not None
        assert persisted_mission.origin_type == "OPPORTUNITY"
        assert persisted_mission.inception_id is None
        assert persisted_mission.opportunity_id == opportunity.id

        events = {
            event.event_type
            for event in (
                await session.scalars(select(Chronicle).where(Chronicle.correlation_id == correlation_id))
            ).all()
        }
        assert "mission_authorization_scoped" in events
        assert "economic_reserved" in events
        assert "economic_committed" in events
        assert "economic_settling" in events
        assert "economic_settled" in events
        assert "learning_episode_recorded" in events

    await engine.dispose()
