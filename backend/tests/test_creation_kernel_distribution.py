from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.models.entities import Agent, Creator, MissionStep, Task, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE chronicles, conscious_memory, universe_memory, mission_memory, conversation_memory, tasks, "
            "mission_steps, mission_plans, missions, inceptions, messages, conversations, agents, universes, creator "
            "RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


@pytest.fixture
async def creator(database):
    creator_id = str(uuid.uuid4())
    async with database() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
    return Actor(creator_id, "creator")


async def authorized_mission(database, creator):
    cid = str(uuid.uuid4())
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Kernel", cid)
        message = await service.add_message(creator, conversation.id, "Build Gate A", {}, cid)
        inception = await service.create_inception(creator, conversation.id, message.id, "Gate A", "Kernel", cid)
        await service.transition_inception(creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, cid)
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, cid)
        mission = await service.create_mission(creator, inception.id, "Kernel", "Close Gate A", cid)
        universe = await service.create_universe(creator, "engineering", "Engineering", cid)
        await service.set_universe_active(creator, universe.id, True, cid)
        await service.create_agent(creator, "engineer", "Engineer", universe.id, {"execute": True}, cid)
        await service.transition_mission(creator, mission.id, MissionStatus.PLANNED, cid, {
            "strategy": "deterministic",
            "steps": [
                {
                    "step_key": "contracts",
                    "title": "Contracts",
                    "description": "Create contracts",
                    "universe": "engineering",
                    "position": 1,
                    "depends_on": [],
                    "completion_criteria": {"done": True},
                },
                {
                    "step_key": "runtime",
                    "title": "Runtime",
                    "description": "Create runtime",
                    "universe": "engineering",
                    "position": 2,
                    "depends_on": ["contracts"],
                    "completion_criteria": {"done": True},
                },
            ],
            "completion_criteria": {"gate_a": True},
        })
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, cid)
        mission = await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, cid)
        return mission.id, cid


@pytest.mark.asyncio
async def test_plan_steps_are_persisted_and_distribution_is_idempotent(database, creator):
    mission_id, cid = await authorized_mission(database, creator)

    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        mission = await service.transition_mission(creator, mission_id, MissionStatus.DISTRIBUTED, cid)
        assert mission.status == "distributed"

    async with database() as session:
        steps = list((await session.scalars(select(MissionStep).order_by(MissionStep.position))).all())
        tasks = list((await session.scalars(select(Task).order_by(Task.created_at))).all())
        assert [step.step_key for step in steps] == ["contracts", "runtime"]
        assert [task.status for task in tasks] == ["READY", "PENDING"]
        assert len({task.idempotency_key for task in tasks}) == 2
        assert all(task.agent_id for task in tasks)

        # Distribution is an exactly-once state transition; repeated calls cannot create duplicate tasks.
        service = LivingCoreService(DomainRepository(session))
        with pytest.raises(Exception):
            await service.transition_mission(creator, mission_id, MissionStatus.DISTRIBUTED, cid)
        await session.rollback()

    async with database() as session:
        assert len((await session.scalars(select(Task))).all()) == 2


@pytest.mark.asyncio
async def test_mission_cannot_manifest_until_all_tasks_succeed(database, creator):
    mission_id, cid = await authorized_mission(database, creator)
    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        await service.transition_mission(creator, mission_id, MissionStatus.DISTRIBUTED, cid)
        await service.transition_mission(creator, mission_id, MissionStatus.EXECUTING, cid)
        with pytest.raises(Exception, match="all Tasks succeed"):
            await service.transition_mission(creator, mission_id, MissionStatus.MANIFESTED, cid)
        await session.rollback()

    async with database() as session:
        tasks = list((await session.scalars(select(Task).where(Task.mission_id == mission_id))).all())
        assert len(tasks) == 2
