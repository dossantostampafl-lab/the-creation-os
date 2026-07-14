from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from db_safety import create_isolated_test_engine
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.entities import Agent, AgentCapability, Capability
from app.repositories.tree_core import TreeCoreRepository
from app.services.tree_core import TreeCoreError, TreeCoreService

pytestmark = pytest.mark.integration


@pytest.fixture
async def tree_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE agent_capabilities, capabilities, tasks, agents, universes, chronicles, "
            "mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


async def create_agent(factory, name="agent", priority=0):
    async with factory() as session:
        service = TreeCoreService(TreeCoreRepository(session))
        return await service.register_agent(name, "test", "central", priority, True)


@pytest.mark.asyncio
async def test_postgres_constraints_foreign_keys_and_cascades(tree_database):
    agent = await create_agent(tree_database)
    async with tree_database() as session:
        service = TreeCoreService(TreeCoreRepository(session))
        capability = await service.create_capability("analysis", "test")
        capability_id = capability.id
        await service.add_capability(agent.id, capability_id)
        duplicate = AgentCapability(agent_id=agent.id, capability_id=capability_id)
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        session.add(AgentCapability(agent_id=str(uuid.uuid4()), capability_id=capability_id))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        await session.execute(delete(Agent).where(Agent.id == agent.id))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AgentCapability)) == 0
        assert await session.get(Capability, capability_id) is not None

        replacement = await service.register_agent("replacement", "test", "central", 0, True)
        await service.add_capability(replacement.id, capability_id)
        await session.execute(delete(Capability).where(Capability.id == capability_id))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AgentCapability)) == 0
        assert await session.get(Agent, replacement.id) is not None


@pytest.mark.asyncio
async def test_postgres_rollback_timestamps_and_session_restart(tree_database):
    transient_id = str(uuid.uuid4())
    async with tree_database() as session:
        session.add(Agent(id=transient_id, name="rollback", description="", universe_name="central",
                          priority=0, status="offline", version=1, enabled=True, active=True,
                          capabilities_json={}))
        await session.flush()
        await session.rollback()
    async with tree_database() as session:
        assert await session.get(Agent, transient_id) is None
        service = TreeCoreService(TreeCoreRepository(session))
        agent = await service.register_agent("persistent", "test", "central", 1, True)
        await service.heartbeat(agent.id, datetime.now(timezone.utc))
        agent_id = agent.id
    async with tree_database() as session:
        persisted = await session.get(Agent, agent_id)
        assert persisted is not None
        assert persisted.created_at.tzinfo is not None
        assert persisted.updated_at.tzinfo is not None
        assert persisted.heartbeat_at is not None and persisted.heartbeat_at.tzinfo is not None


@pytest.mark.asyncio
async def test_concurrent_heartbeats_and_enable_disable(tree_database):
    agent = await create_agent(tree_database)

    async def heartbeat():
        async with tree_database() as session:
            await TreeCoreService(TreeCoreRepository(session)).heartbeat(agent.id)

    await asyncio.gather(heartbeat(), heartbeat())
    async with tree_database() as session:
        persisted = await session.get(Agent, agent.id)
        assert persisted.status == "idle" and persisted.version == 3

    async def toggle(enable):
        async with tree_database() as session:
            service = TreeCoreService(TreeCoreRepository(session))
            return await (service.enable(agent.id) if enable else service.disable(agent.id))

    await asyncio.gather(toggle(True), toggle(False))
    async with tree_database() as session:
        persisted = await session.get(Agent, agent.id)
        assert (persisted.enabled, persisted.status) in {(True, "offline"), (False, "disabled")}
        assert persisted.version == 5


@pytest.mark.asyncio
async def test_concurrent_duplicate_capability_operations(tree_database):
    agent = await create_agent(tree_database)
    async with tree_database() as session:
        capability = await TreeCoreService(TreeCoreRepository(session)).create_capability("analysis", "test")

    async def assign():
        async with tree_database() as session:
            try:
                await TreeCoreService(TreeCoreRepository(session)).add_capability(agent.id, capability.id)
                return "created"
            except TreeCoreError:
                return "conflict"

    assert sorted(await asyncio.gather(assign(), assign())) == ["conflict", "created"]

    async def create_capability():
        async with tree_database() as session:
            try:
                await TreeCoreService(TreeCoreRepository(session)).create_capability("  PLANNING ", "test")
                return "created"
            except TreeCoreError:
                return "conflict"

    assert sorted(await asyncio.gather(create_capability(), create_capability())) == ["conflict", "created"]
