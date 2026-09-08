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
from app.kernel.completion_engine import MissionCompletionEngine
from app.models.entities import Creator, Mission, Task
from app.models.execution import AgentExecution
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


class TransientFailureProvider:
    name = "chaos"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient provider fault")
        return InferenceResponse(
            provider=self.name,
            model=request.model or "chaos-model",
            content="recovered",
            metadata={"recovered_after_transient_fault": True},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


@pytest.fixture
async def chaos_db():
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
async def test_transient_provider_failure_retries_and_manifestation_recovers(chaos_db):
    creator_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    creator = Actor(creator_id, "creator")

    async with chaos_db() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Chaos", correlation_id)
        message = await service.add_message(creator, conversation.id, "Recover from provider fault", {}, correlation_id)
        inception = await service.create_inception(
            creator,
            conversation.id,
            message.id,
            "Chaos recovery",
            "Prove retry after a transient inference failure",
            correlation_id,
        )
        await service.transition_inception(
            creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id
        )
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, correlation_id)
        universe = await service.create_universe(creator, "chaos", "Chaos", correlation_id)
        await service.set_universe_active(creator, universe.id, True, correlation_id)
        await service.create_agent(
            creator,
            "chaos-agent",
            "Chaos Agent",
            universe.id,
            {"inference_provider": "chaos", "model": "chaos-model"},
            correlation_id,
        )
        mission = await service.create_mission(
            creator, inception.id, "Chaos Mission", "Recover and manifest", correlation_id
        )
        await service.transition_mission(
            creator,
            mission.id,
            MissionStatus.PLANNED,
            correlation_id,
            {
                "strategy": "retry transient provider fault",
                "steps": [{
                    "step_key": "recover",
                    "title": "Recover",
                    "description": "Complete after one transient inference failure",
                    "universe": "chaos",
                    "position": 1,
                    "depends_on": [],
                    "completion_criteria": {"recovered": True},
                }],
                "completion_criteria": {"all_tasks_succeeded": True},
            },
        )
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.DISTRIBUTED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.EXECUTING, correlation_id)
        mission_id = mission.id

    provider = TransientFailureProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    runtime = AgentRuntime(
        chaos_db,
        ModelRouter(registry),
        completion_engine=MissionCompletionEngine(chaos_db),
    )

    assert await runtime.run_next(mission_id, correlation_id) is True
    async with chaos_db() as session:
        task = await session.scalar(select(Task).where(Task.mission_id == mission_id))
        mission = await session.get(Mission, mission_id)
        assert task is not None and task.status == "READY"
        assert task.attempt_count == 1
        assert task.error_json["code"] == "INFERENCE_ERROR"
        assert mission is not None and mission.status == MissionStatus.EXECUTING.value

    assert await runtime.run_next(mission_id, correlation_id) is True

    async with chaos_db() as session:
        task = await session.scalar(select(Task).where(Task.mission_id == mission_id))
        mission = await session.get(Mission, mission_id)
        assert task is not None and task.status == "SUCCEEDED"
        executions = list((await session.scalars(
            select(AgentExecution).where(AgentExecution.task_id == task.id).order_by(AgentExecution.attempt)
        )).all())
        assert provider.calls == 2
        assert task.attempt_count == 2
        assert mission is not None and mission.status == MissionStatus.MANIFESTED.value
        assert [execution.status for execution in executions] == ["FAILED", "SUCCEEDED"]
        assert executions[0].error_json["code"] == "INFERENCE_ERROR"
        assert executions[1].provider == "chaos"
