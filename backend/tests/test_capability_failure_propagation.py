from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.capabilities.contracts import CapabilityResult
from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.inference.contracts import InferenceRequest, InferenceResponse, ProviderHealth
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.kernel.agent_runtime import AgentRuntime
from app.kernel.completion_engine import MissionCompletionEngine
from app.models.entities import Creator, Mission, Task
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


class CapabilityFailureProvider:
    name = "capability-failure"

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            provider=self.name,
            model=request.model or "capability-failure-model",
            content="capability requested",
            metadata={
                "capability_intent": {
                    "capability": "proto",
                    "action": "submit_mission",
                    "arguments": {},
                }
            },
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


class FailingCapabilityRuntime:
    async def execute(self, **_: Any) -> CapabilityResult:
        return CapabilityResult(
            capability="proto",
            action="submit_mission",
            ok=False,
            data={"state": "BLOCKED"},
            error={"code": "PROTO_MISSION_NOT_COMPLETED", "detail": "BLOCKED"},
        )


@pytest.fixture
async def failure_db():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE projection_checkpoints, capability_invocations, agent_executions, chronicles, pulse_metrics, "
                "conscious_memory, universe_memory, mission_memory, conversation_memory, tasks, mission_steps, "
                "mission_plans, missions, inceptions, messages, conversations, agents, universes, creator "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_capability_result_fails_task_and_mission(failure_db) -> None:
    creator_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    creator = Actor(creator_id, "creator")

    async with failure_db() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Capability Failure", correlation_id)
        message = await service.add_message(
            creator,
            conversation.id,
            "Exercise a failing governed capability",
            {},
            correlation_id,
        )
        inception = await service.create_inception(
            creator,
            conversation.id,
            message.id,
            "Capability Failure",
            "A failed capability must fail its task",
            correlation_id,
        )
        await service.transition_inception(
            creator,
            inception.id,
            InceptionStatus.AWAITING_CREATOR_DECISION,
            correlation_id,
        )
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, correlation_id)
        universe = await service.create_universe(creator, "cap-failure", "Capability Failure", correlation_id)
        await service.set_universe_active(creator, universe.id, True, correlation_id)
        await service.create_agent(
            creator,
            "capability-failure-agent",
            "Capability Failure Agent",
            universe.id,
            {"inference_provider": "capability-failure", "model": "capability-failure-model"},
            correlation_id,
        )
        mission = await service.create_mission(
            creator,
            inception.id,
            "Capability Failure Mission",
            "A blocked external capability must not manifest a mission",
            correlation_id,
        )
        await service.transition_mission(
            creator,
            mission.id,
            MissionStatus.PLANNED,
            correlation_id,
            {
                "strategy": "single failing capability step",
                "steps": [
                    {
                        "step_key": "call_proto",
                        "title": "Call PROTO",
                        "description": "Request a governed PROTO capability",
                        "universe": "cap-failure",
                        "position": 1,
                        "depends_on": [],
                        "completion_criteria": {"capability_succeeded": True},
                    }
                ],
                "completion_criteria": {"all_tasks_succeeded": True},
            },
        )
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.DISTRIBUTED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.EXECUTING, correlation_id)
        mission_id = mission.id

    registry = ProviderRegistry()
    registry.register(CapabilityFailureProvider())
    runtime = AgentRuntime(
        failure_db,
        ModelRouter(registry),
        capability_runtime=FailingCapabilityRuntime(),  # type: ignore[arg-type]
        completion_engine=MissionCompletionEngine(failure_db),
    )

    assert await runtime.run_next(mission_id, correlation_id) is True

    async with failure_db() as session:
        mission = await session.get(Mission, mission_id)
        task = await session.scalar(select(Task).where(Task.mission_id == mission_id))
        assert mission is not None and mission.status == MissionStatus.FAILED.value
        assert task is not None and task.status == "FAILED"
