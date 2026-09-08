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
from app.models.entities import Chronicle, Creator, Mission, Task
from app.models.execution import AgentExecution
from app.projections.system import system_snapshot
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = pytest.mark.integration


class DeterministicGauntletProvider:
    name = "gauntlet"

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            provider=self.name,
            model=request.model or "gauntlet-model",
            content="authorized task completed",
            metadata={"gauntlet": True},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


@pytest.fixture
async def gauntlet_db():
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
async def test_creator_to_manifested_mission_is_causally_complete_and_projectable(gauntlet_db):
    creator_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    creator = Actor(creator_id, "creator")

    async with gauntlet_db() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))

        conversation = await service.create_conversation(creator, "Gate E", correlation_id)
        message = await service.add_message(
            creator,
            conversation.id,
            "Manifest the deterministic system gauntlet mission",
            {},
            correlation_id,
        )
        inception = await service.create_inception(
            creator,
            conversation.id,
            message.id,
            "System Gauntlet",
            "Exercise the full sovereign mission path",
            correlation_id,
        )
        await service.transition_inception(
            creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id
        )
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, correlation_id)

        universe = await service.create_universe(creator, "gauntlet", "Gauntlet", correlation_id)
        await service.set_universe_active(creator, universe.id, True, correlation_id)
        await service.create_agent(
            creator,
            "gauntlet-agent",
            "Gauntlet Agent",
            universe.id,
            {"inference_provider": "gauntlet", "model": "gauntlet-model"},
            correlation_id,
        )

        mission = await service.create_mission(
            creator, inception.id, "Gate E Mission", "Prove deterministic manifestation", correlation_id
        )
        await service.transition_mission(
            creator,
            mission.id,
            MissionStatus.PLANNED,
            correlation_id,
            {
                "strategy": "sequential deterministic gauntlet",
                "steps": [
                    {
                        "step_key": "observe",
                        "title": "Observe",
                        "description": "Observe the authorized mission state",
                        "universe": "gauntlet",
                        "position": 1,
                        "depends_on": [],
                        "completion_criteria": {"provider_response": True},
                    },
                    {
                        "step_key": "manifest",
                        "title": "Manifest",
                        "description": "Complete the dependent mission work",
                        "universe": "gauntlet",
                        "position": 2,
                        "depends_on": ["observe"],
                        "completion_criteria": {"provider_response": True},
                    },
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
    registry.register(DeterministicGauntletProvider())
    completion = MissionCompletionEngine(gauntlet_db)
    runtime = AgentRuntime(gauntlet_db, ModelRouter(registry), completion_engine=completion)

    assert await runtime.run_next(mission_id, correlation_id) is True
    assert await runtime.run_next(mission_id, correlation_id) is True
    assert await runtime.run_next(mission_id, correlation_id) is False

    async with gauntlet_db() as session:
        mission = await session.get(Mission, mission_id)
        assert mission is not None
        assert mission.status == MissionStatus.MANIFESTED.value
        assert mission.completed_at is not None

        tasks = list((await session.scalars(
            select(Task).where(Task.mission_id == mission_id).order_by(Task.created_at, Task.id)
        )).all())
        executions = list((await session.scalars(select(AgentExecution).order_by(AgentExecution.started_at))).all())
        assert [task.status for task in tasks] == ["SUCCEEDED", "SUCCEEDED"]
        assert [execution.status for execution in executions] == ["SUCCEEDED", "SUCCEEDED"]
        assert all(execution.provider == "gauntlet" for execution in executions)

        chronicle_types = list((await session.scalars(
            select(Chronicle.event_type).order_by(Chronicle.position)
        )).all())
        required = {
            "conversation_created",
            "conversation_message_added",
            "inception_created",
            "inception_approved",
            "mission_created",
            "mission_planned",
            "mission_validated",
            "mission_authorized",
            "mission_distributed",
            "mission_execution_started",
            "mission_manifested",
        }
        assert required <= set(chronicle_types)

        integrity = await DomainRepository(session).verify_chronicle()
        assert integrity.valid is True

        snapshot = await system_snapshot(session, persist=False)
        projected_mission = next(item for item in snapshot["missions"] if item["id"] == mission_id)
        assert projected_mission["status"] == "manifested"
        assert snapshot["counts"]["running_missions"] == 0
        assert snapshot["counts"]["failed_tasks"] == 0
