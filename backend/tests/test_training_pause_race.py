from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from stf_database import stf_db  # noqa: F401

from app.core.domain import Actor
from app.models.entities import Agent, Creator, Universe
from app.models.security_task_force import StfRun
from app.repositories.domain import DomainRepository
from app.security_task_force.service import StfService
from app.security_task_force.training import (
    TRAINING_AGENT_SPECS,
    AutomaticRangeTraining,
    ensure_training_agents,
)
from app.services.domain import LivingCoreService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_waits_for_selected_training_cycle_then_prevents_new_cycle(stf_db, monkeypatch) -> None:  # noqa: F811
    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    selected_code = TRAINING_AGENT_SPECS[0].code
    async with factory() as session:
        if await session.scalar(select(Universe.id).where(Universe.code == "security")) is None:
            session.add(Universe(id=str(uuid.uuid4()), code="security", name="Segurança", active=True))
            await session.flush()
        agents = await ensure_training_agents(session)
        selected = next(agent for agent in agents if agent.code == selected_code)
        agent_id, original_active = selected.id, selected.active
        selected.active = True
        session.add(Creator(id=creator_id, username="creator-pause-race", password_hash="unused", is_active=True))
        await session.commit()

    selection_ready = asyncio.Event()
    release_queue = asyncio.Event()
    pause_attempted = asyncio.Event()
    backend_pids: dict[str, int] = {}
    original_start = StfService.start

    async def gated_start(self, *args, **kwargs):
        backend_pids["scheduler"] = await self.session.scalar(text("SELECT pg_backend_pid()"))
        selection_ready.set()
        await release_queue.wait()
        return await original_start(self, *args, **kwargs)

    monkeypatch.setattr(StfService, "start", gated_start)
    coordinator = AutomaticRangeTraining(factory)
    scheduler = asyncio.create_task(coordinator.run_once(creator_id, agent_code=selected_code))
    pause = None

    async def pause_selected_agent():
        async with factory() as session:
            backend_pids["pause"] = await session.scalar(text("SELECT pg_backend_pid()"))
            pause_attempted.set()
            await LivingCoreService(DomainRepository(session)).set_agent_active(
                Actor(creator_id, "creator"), agent_id, False, str(uuid.uuid4())
            )

    try:
        await asyncio.wait_for(selection_ready.wait(), timeout=5)
        pause = asyncio.create_task(pause_selected_agent())
        await asyncio.wait_for(pause_attempted.wait(), timeout=5)

        async def assert_real_database_lock_wait():
            async with factory() as session:
                while True:
                    # Observe an actual PostgreSQL blocker, rather than relying on task scheduling.
                    blockers = await session.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": backend_pids["pause"]}
                    )
                    if backend_pids["scheduler"] in blockers:
                        return
                    assert not pause.done(), "Pause committed while the scheduler still held its selected roster"
                    await asyncio.sleep(0.01)

        await asyncio.wait_for(assert_real_database_lock_wait(), timeout=5)
        assert not pause.done()
        release_queue.set()
        queued, _ = await asyncio.wait_for(asyncio.gather(scheduler, pause), timeout=10)
        assert queued["status"] == "queued"
        assert queued["agent_code"] == selected_code

        async with factory() as session:
            assert await session.scalar(select(Agent.active).where(Agent.id == agent_id)) is False
            assert await session.scalar(select(func.count()).select_from(StfRun).where(StfRun.creator_id == creator_id)) == 1
        with pytest.raises(ValueError, match="paused"):
            await coordinator.run_once(creator_id, agent_code=selected_code)
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(StfRun).where(StfRun.creator_id == creator_id)) == 1
    finally:
        release_queue.set()
        pending = [task for task in (scheduler, pause) if task is not None]
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        async with factory() as session:
            restored = await session.get(Agent, agent_id)
            if restored is not None:
                restored.active = original_active
            await session.commit()
