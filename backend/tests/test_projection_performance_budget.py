from __future__ import annotations

import os
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Agent, Universe
from app.projections.system import system_snapshot

pytestmark = pytest.mark.integration

PROJECTION_BUDGET_SECONDS = 2.0
ENTITY_COUNT = 100


@pytest.fixture
async def performance_db():
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
async def test_system_projection_stays_within_smoke_latency_budget(performance_db):
    async with performance_db() as session:
        universes = [
            Universe(id=str(uuid.uuid4()), code=f"perf-{index:03d}", name=f"Performance {index}", active=True)
            for index in range(ENTITY_COUNT)
        ]
        session.add_all(universes)
        await session.flush()
        session.add_all([
            Agent(
                id=str(uuid.uuid4()),
                code=f"perf-agent-{index:03d}",
                name=f"Performance Agent {index}",
                universe_id=universe.id,
                active=True,
                capabilities_json={},
            )
            for index, universe in enumerate(universes)
        ])
        await session.commit()

    async with performance_db() as session:
        started = time.perf_counter()
        snapshot = await system_snapshot(session, persist=False)
        elapsed = time.perf_counter() - started

    assert snapshot["counts"]["active_universes"] == ENTITY_COUNT
    assert snapshot["counts"]["active_agents"] == ENTITY_COUNT
    assert elapsed < PROJECTION_BUDGET_SECONDS, (
        f"system projection exceeded smoke latency budget: {elapsed:.3f}s >= {PROJECTION_BUDGET_SECONDS:.3f}s"
    )
