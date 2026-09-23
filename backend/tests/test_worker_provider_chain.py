from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.inference.contracts import (
    InferenceRequest,
    InferenceResponse,
    ProviderHealth,
    ProviderUnavailable,
)
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.kernel.agent_runtime import AgentRuntime
from app.kernel.completion_engine import MissionCompletionEngine
from app.models.entities import Task
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


class UnavailableProvider:
    name = "freellmapi"

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        raise ProviderUnavailable(self.name, "primary provider down")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=False, detail="primary provider down")


class ReserveProvider:
    name = "anthropic"

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            provider=self.name,
            model=request.model or "reserve-model",
            content="answered by the reserve provider",
            metadata={},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


@pytest.fixture
async def chain_db():
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


async def _seed_mission(factory, creator: Actor, correlation_id: str) -> str:
    from app.models.entities import Creator

    async with factory() as session:
        session.add(Creator(id=creator.id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Chain", correlation_id)
        message = await service.add_message(
            creator, conversation.id, "Use the reserve provider", {}, correlation_id
        )
        inception = await service.create_inception(
            creator,
            conversation.id,
            message.id,
            "Provider chain",
            "Prove the configured fallback chain reaches the worker",
            correlation_id,
        )
        await service.transition_inception(
            creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id
        )
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, correlation_id)
        universe = await service.create_universe(creator, "chain", "Chain", correlation_id)
        await service.set_universe_active(creator, universe.id, True, correlation_id)
        await service.create_agent(
            creator,
            "chain-agent",
            "Chain Agent",
            universe.id,
            {"inference_provider": "freellmapi"},
            correlation_id,
        )
        mission = await service.create_mission(
            creator, inception.id, "Chain Mission", "Fall back to the reserve", correlation_id
        )
        await service.transition_mission(
            creator,
            mission.id,
            MissionStatus.PLANNED,
            correlation_id,
            {
                "strategy": "fall back to the configured reserve provider",
                "steps": [{
                    "step_key": "answer",
                    "title": "Answer",
                    "description": "Complete through the reserve provider",
                    "universe": "chain",
                    "position": 1,
                    "depends_on": [],
                    "completion_criteria": {"answered": True},
                }],
                "completion_criteria": {"all_tasks_succeeded": True},
            },
        )
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.DISTRIBUTED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.EXECUTING, correlation_id)
        return mission.id


@pytest.mark.asyncio
async def test_worker_uses_the_configured_fallback_when_the_agent_declares_none(
    chain_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")

    creator = Actor(str(uuid.uuid4()), "creator")
    correlation_id = str(uuid.uuid4())
    mission_id = await _seed_mission(chain_db, creator, correlation_id)

    registry = ProviderRegistry()
    registry.register(UnavailableProvider())
    registry.register(ReserveProvider())
    runtime = AgentRuntime(
        chain_db,
        ModelRouter(registry),
        completion_engine=MissionCompletionEngine(chain_db),
    )

    assert await runtime.run_next(mission_id, correlation_id) is True

    async with chain_db() as session:
        task = await session.scalar(select(Task).where(Task.mission_id == mission_id))
        assert task is not None and task.status == "SUCCEEDED"
