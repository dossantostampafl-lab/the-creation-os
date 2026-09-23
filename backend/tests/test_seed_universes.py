from __future__ import annotations

import os
import uuid

import bcrypt
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.admin.seed as seed
from app.admin.seed import UNIVERSES, seed_universes
from app.config import settings
from app.models.entities import Agent, Chronicle, Creator, Universe

pytestmark = pytest.mark.integration


@pytest.fixture
async def database(monkeypatch):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE chronicles, agent_executions, tasks, mission_steps, mission_plans, missions, inceptions, "
            "messages, conversations, agents, universes, creator RESTART IDENTITY CASCADE"
        ))
    monkeypatch.setattr(seed, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


async def add_creator(factory) -> str:
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(
            id=creator_id,
            username=settings.creator_bootstrap_username,
            password_hash=bcrypt.hashpw(b"unused", bcrypt.gensalt()).decode("ascii"),
            is_active=True,
        ))
        await session.commit()
    return creator_id


@pytest.mark.asyncio
async def test_seed_refuses_before_the_creator_exists(database) -> None:
    assert await seed_universes() == 1

    async with database() as session:
        assert (await session.scalars(select(Universe))).all() == []


@pytest.mark.asyncio
async def test_seed_refuses_when_the_creator_is_not_the_sovereign(database, monkeypatch) -> None:
    await add_creator(database)
    monkeypatch.setattr(settings, "sovereign_creator_id", str(uuid.uuid4()))

    assert await seed_universes() == 1

    async with database() as session:
        assert (await session.scalars(select(Universe))).all() == []


@pytest.mark.asyncio
async def test_seed_makes_every_universe_able_to_take_a_mission_step(database, monkeypatch) -> None:
    creator_id = await add_creator(database)
    monkeypatch.setattr(settings, "sovereign_creator_id", creator_id)
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")

    assert await seed_universes() == 0

    async with database() as session:
        universes = {item.code: item for item in (await session.scalars(select(Universe))).all()}
        agents = {item.code: item for item in (await session.scalars(select(Agent))).all()}
        assert sorted(universes) == sorted(code for code, _, _ in UNIVERSES)
        for code, _, _ in UNIVERSES:
            assert universes[code].active, f"{code} must be active to take a step"
            agent = agents[f"{code}-agent"]
            assert agent.active and agent.universe_id == universes[code].id
            # Without this the Agent's first task fails with "Agent has no inference_provider".
            assert agent.capabilities_json["inference_provider"] == "freellmapi"
        events = [item.event_type for item in (await session.scalars(select(Chronicle))).all()]
        assert events.count("universe_created") == len(UNIVERSES)
        assert events.count("agent_created") == len(UNIVERSES)


@pytest.mark.asyncio
async def test_seed_run_again_changes_nothing(database, monkeypatch) -> None:
    creator_id = await add_creator(database)
    monkeypatch.setattr(settings, "sovereign_creator_id", creator_id)
    assert await seed_universes() == 0

    async with database() as session:
        before = [item.id for item in (await session.scalars(select(Universe))).all()]
        chronicle_before = len((await session.scalars(select(Chronicle))).all())

    assert await seed_universes() == 0

    async with database() as session:
        assert [item.id for item in (await session.scalars(select(Universe))).all()] == before
        assert len((await session.scalars(select(Chronicle))).all()) == chronicle_before


@pytest.mark.asyncio
async def test_seed_reactivates_a_universe_or_agent_that_was_turned_off(database, monkeypatch) -> None:
    creator_id = await add_creator(database)
    monkeypatch.setattr(settings, "sovereign_creator_id", creator_id)
    assert await seed_universes() == 0

    code = UNIVERSES[0][0]
    async with database() as session:
        universe = await session.scalar(select(Universe).where(Universe.code == code))
        agent = await session.scalar(select(Agent).where(Agent.code == f"{code}-agent"))
        universe.active = False
        agent.active = False
        await session.commit()

    assert await seed_universes() == 0

    async with database() as session:
        universe = await session.scalar(select(Universe).where(Universe.code == code))
        agent = await session.scalar(select(Agent).where(Agent.code == f"{code}-agent"))
        assert universe.active and agent.active
