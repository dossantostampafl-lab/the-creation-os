from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.capabilities.contracts import CapabilityIntent, CapabilityResult, MissionAuthorization
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.mission_authorization import set_mission_authorization
from app.capabilities.policy import CapabilityDenied
from app.capabilities.runtime import CapabilityRuntime
from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.models.entities import Creator
from app.models.execution import CapabilityInvocation
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


class EchoAdapter:
    name = "echo"

    async def execute(self, intent: CapabilityIntent) -> CapabilityResult:
        return CapabilityResult(
            capability=intent.capability,
            action=intent.action,
            ok=True,
            data={"echo": intent.arguments},
        )


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE capability_invocations, agent_executions, chronicles, tasks, mission_steps, mission_plans, "
            "missions, inceptions, messages, conversations, agents, universes, creator RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


async def authorized_mission(database) -> tuple[Actor, str]:
    creator_id = str(uuid.uuid4())
    actor = Actor(creator_id, "creator")
    cid = str(uuid.uuid4())
    async with database() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(actor, "Capabilities", cid)
        message = await service.add_message(actor, conversation.id, "Use a bounded capability", {}, cid)
        inception = await service.create_inception(actor, conversation.id, message.id, "Capability", "Bounded action", cid)
        await service.transition_inception(actor, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, cid)
        await service.transition_inception(actor, inception.id, InceptionStatus.APPROVED, cid)
        mission = await service.create_mission(actor, inception.id, "Capability mission", "Execute safely", cid)
        await service.transition_mission(actor, mission.id, MissionStatus.PLANNED, cid, {
            "strategy": "bounded",
            "steps": [{
                "step_key": "echo",
                "title": "Echo",
                "description": "Use echo capability",
                "universe": "engineering",
                "position": 1,
                "depends_on": [],
                "completion_criteria": {"done": True},
            }],
            "completion_criteria": {"done": True},
        })
        await service.transition_mission(actor, mission.id, MissionStatus.VALIDATED, cid)
        await service.transition_mission(actor, mission.id, MissionStatus.AUTHORIZED, cid)
        await set_mission_authorization(
            service.repo,
            actor=actor,
            mission_id=mission.id,
            authorization={
                "allowed_capabilities": ["echo"],
                "denied_capabilities": [],
                "scope": {"actions": {"echo": ["say"]}},
                "external_effects_allowed": False,
                "risk_level": "low",
                "budget": {},
                "expires_at": None,
                "version": 1,
            },
            correlation_id=cid,
        )
        return actor, mission.id


@pytest.mark.asyncio
async def test_capability_runtime_persists_authorized_and_successful_invocation(database):
    _, mission_id = await authorized_mission(database)
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    runtime = CapabilityRuntime(database, gateway)
    authorization = MissionAuthorization(
        allowed_capabilities=["echo"],
        scope={"actions": {"echo": ["say"]}},
        authorized_by="creator",
        authorized_at="2026-09-08T00:00:00Z",
    )

    result = await runtime.execute(
        mission_id=mission_id,
        task_id=None,
        agent_execution_id=None,
        intent=CapabilityIntent(capability="echo", action="say", arguments={"value": "hello"}),
        authorization=authorization,
    )
    assert result.ok is True

    async with database() as session:
        rows = list((await session.scalars(select(CapabilityInvocation))).all())
        assert len(rows) == 1
        assert rows[0].status == "SUCCEEDED"
        assert rows[0].result_json["data"] == {"echo": {"value": "hello"}}


@pytest.mark.asyncio
async def test_capability_runtime_persists_denial_before_adapter_execution(database):
    _, mission_id = await authorized_mission(database)
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    runtime = CapabilityRuntime(database, gateway)
    authorization = MissionAuthorization(
        allowed_capabilities=[],
        denied_capabilities=["echo"],
        authorized_by="creator",
        authorized_at="2026-09-08T00:00:00Z",
    )

    with pytest.raises(CapabilityDenied):
        await runtime.execute(
            mission_id=mission_id,
            task_id=None,
            agent_execution_id=None,
            intent=CapabilityIntent(capability="echo", action="say"),
            authorization=authorization,
        )

    async with database() as session:
        row = await session.scalar(select(CapabilityInvocation))
        assert row is not None
        assert row.status == "DENIED"
        assert row.error_json["code"] == "CAPABILITY_DENIED"
