from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.inference.contracts import InferenceRequest, InferenceResponse, ProviderHealth
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.kernel.agent_runtime import AgentRuntime
from app.models.entities import Creator, Task
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


class CountingProvider:
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
        return InferenceResponse(provider=self.name, model="counting-model", content="should not run")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE projection_checkpoints, capability_invocations, agent_executions, chronicles, pulse_metrics, "
            "conscious_memory, universe_memory, mission_memory, conversation_memory, tasks, mission_steps, "
            "mission_plans, missions, inceptions, messages, conversations, agents, universes, creator "
            "RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_mission_cancels_pending_work_and_runtime_does_not_call_provider(database):
    creator_id = str(uuid.uuid4())
    creator = Actor(creator_id, "creator")
    cid = str(uuid.uuid4())

    async with database() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Cancel", cid)
        message = await service.add_message(creator, conversation.id, "Cancel safely", {}, cid)
        inception = await service.create_inception(creator, conversation.id, message.id, "Cancel", "Cancel", cid)
        await service.transition_inception(creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, cid)
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, cid)
        universe = await service.create_universe(creator, "cancel", "Cancel", cid)
        await service.set_universe_active(creator, universe.id, True, cid)
        await service.create_agent(
            creator,
            "cancel-agent",
            "Cancel Agent",
            universe.id,
            {"inference_provider": "counting", "model": "counting-model"},
            cid,
        )
        mission = await service.create_mission(creator, inception.id, "Cancellation", "Prove no work after cancel", cid)
        await service.transition_mission(creator, mission.id, MissionStatus.PLANNED, cid, {
            "strategy": "cancel-before-execute",
            "steps": [{
                "step_key": "work",
                "title": "Work",
                "description": "Must never execute after cancellation",
                "universe": "cancel",
                "position": 1,
                "depends_on": [],
                "completion_criteria": {"never_after_cancel": True},
            }],
        })
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.DISTRIBUTED, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.EXECUTING, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.CANCELLED, cid)
        mission_id = mission.id

    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    runtime = AgentRuntime(database, ModelRouter(registry))

    assert await runtime.run_next(mission_id, cid) is False
    assert provider.calls == 0

    async with database() as session:
        tasks = list((await session.scalars(select(Task).where(Task.mission_id == mission_id))).all())
        assert len(tasks) == 1
        assert tasks[0].status == "CANCELLED"
        assert tasks[0].completed_at is not None
