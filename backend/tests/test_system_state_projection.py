from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.domain import Actor
from app.models.entities import Creator
from app.projections.system import system_snapshot
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE projection_checkpoints, capability_invocations, agent_executions, chronicles, tasks, "
            "mission_steps, mission_plans, missions, inceptions, messages, conversations, agents, universes, "
            "creator RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_system_snapshot_contains_only_persisted_state(database):
    creator_id = str(uuid.uuid4())
    actor = Actor(creator_id, "creator")
    cid = str(uuid.uuid4())
    async with database() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()

    async with database() as session:
        service = LivingCoreService(DomainRepository(session))
        await service.create_conversation(actor, "State", cid)
        universe = await service.create_universe(actor, "engineering", "Engineering", cid)
        await service.set_universe_active(actor, universe.id, True, cid)
        await service.create_agent(actor, "engineer", "Engineer", universe.id, {}, cid)

    async with database() as session:
        snapshot = await system_snapshot(session)
        assert snapshot["position"] == 4
        assert snapshot["counts"] == {
            "missions": 0,
            "running_missions": 0,
            "tasks": 0,
            "ready_tasks": 0,
            "running_tasks": 0,
            "failed_tasks": 0,
            "active_universes": 1,
            "active_agents": 1,
        }
        assert snapshot["universes"] == [{
            "id": universe.id,
            "code": "engineering",
            "name": "Engineering",
            "active": True,
        }]
        assert snapshot["agents"][0]["code"] == "engineer"
