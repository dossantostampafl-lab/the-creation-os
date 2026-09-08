from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.inference.bootstrap import build_model_router
from app.kernel.agent_runtime import AgentRuntime
from app.kernel.completion_engine import MissionCompletionEngine
from app.models.entities import Creator, Mission, Task
from app.models.execution import AgentExecution
from app.repositories.domain import DomainRepository
from app.services.domain import LivingCoreService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_provider,
    pytest.mark.skipif(
        os.getenv("REAL_PROVIDER_TEST") != "1",
        reason="real provider mission requires explicit REAL_PROVIDER_TEST=1",
    ),
]


@pytest.fixture
async def real_provider_db():
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
async def test_real_provider_completes_authorized_mission_to_manifested(real_provider_db):
    assert settings.app_env == "test"
    assert settings.llm_provider == "openai"
    assert settings.llm_api_key is not None and settings.llm_api_key.get_secret_value()
    assert settings.llm_model and settings.llm_model != "fake"

    creator_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    creator = Actor(creator_id, "creator")

    async with real_provider_db() as session:
        session.add(Creator(id=creator_id, username="real-provider-creator", password_hash="unused", is_active=True))
        await session.commit()
        service = LivingCoreService(DomainRepository(session))
        conversation = await service.create_conversation(creator, "Real Provider Gate", correlation_id)
        message = await service.add_message(
            creator,
            conversation.id,
            "Return a concise confirmation that this authorized validation task completed.",
            {},
            correlation_id,
        )
        inception = await service.create_inception(
            creator,
            conversation.id,
            message.id,
            "Real Provider Mission",
            "Validate the operational inference boundary with a real provider",
            correlation_id,
        )
        await service.transition_inception(
            creator, inception.id, InceptionStatus.AWAITING_CREATOR_DECISION, correlation_id
        )
        await service.transition_inception(creator, inception.id, InceptionStatus.APPROVED, correlation_id)
        universe = await service.create_universe(creator, "real-provider", "Real Provider", correlation_id)
        await service.set_universe_active(creator, universe.id, True, correlation_id)
        await service.create_agent(
            creator,
            "real-provider-agent",
            "Real Provider Agent",
            universe.id,
            {
                "inference_provider": "openai",
                "model": settings.llm_model,
            },
            correlation_id,
        )
        mission = await service.create_mission(
            creator,
            inception.id,
            "Real Provider Mission",
            "Prove a real provider can complete an authorized mission",
            correlation_id,
        )
        await service.transition_mission(
            creator,
            mission.id,
            MissionStatus.PLANNED,
            correlation_id,
            {
                "strategy": "single real-provider validation step",
                "steps": [{
                    "step_key": "real_provider_validation",
                    "title": "Real provider validation",
                    "description": "Return a concise textual confirmation only; request no capability or external action.",
                    "universe": "real-provider",
                    "position": 1,
                    "depends_on": [],
                    "completion_criteria": {"nonempty_provider_response": True},
                }],
                "completion_criteria": {"all_tasks_succeeded": True},
            },
        )
        await service.transition_mission(creator, mission.id, MissionStatus.VALIDATED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.AUTHORIZED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.DISTRIBUTED, correlation_id)
        await service.transition_mission(creator, mission.id, MissionStatus.EXECUTING, correlation_id)
        mission_id = mission.id

    runtime = AgentRuntime(
        real_provider_db,
        build_model_router(),
        completion_engine=MissionCompletionEngine(real_provider_db),
    )
    assert await runtime.run_next(mission_id, correlation_id) is True

    async with real_provider_db() as session:
        mission = await session.get(Mission, mission_id)
        task = await session.scalar(select(Task).where(Task.mission_id == mission_id))
        assert mission is not None and mission.status == MissionStatus.MANIFESTED.value
        assert task is not None and task.status == "SUCCEEDED"
        executions = list((await session.scalars(
            select(AgentExecution).where(AgentExecution.task_id == task.id)
        )).all())
        assert len(executions) == 1
        assert executions[0].status == "SUCCEEDED"
        assert executions[0].provider == "openai"
        assert executions[0].model
        assert str((executions[0].output_json or {}).get("content", "")).strip()
