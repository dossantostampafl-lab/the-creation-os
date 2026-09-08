from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.kernel.reconciler import ExecutionReconciler
from app.models.entities import Agent, Conversation, Creator, Inception, Message, Mission, MissionPlan, MissionStep, Task, Universe
from app.models.execution import AgentExecution, CapabilityInvocation

pytestmark = pytest.mark.integration


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE capability_invocations, agent_executions, chronicles, tasks, mission_steps, mission_plans, "
            "missions, inceptions, messages, conversations, agents, universes, creator RESTART IDENTITY CASCADE"
        ))
    yield factory
    await engine.dispose()


async def running_attempt(database, *, at_most_once: bool) -> tuple[str, str, str | None]:
    creator_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    inception_id = str(uuid.uuid4())
    mission_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    invocation_id = str(uuid.uuid4()) if at_most_once else None

    async with database() as session:
        session.add_all([
            Creator(id=creator_id, username="creator", password_hash="unused", is_active=True),
            Conversation(id=conversation_id, creator_id=creator_id, title="Restart", status="active"),
            Message(
                id=message_id,
                conversation_id=conversation_id,
                role="creator",
                actor_id=creator_id,
                correlation_id=str(uuid.uuid4()),
                content="restart",
                route="deus",
                metadata_json={},
            ),
            Inception(
                id=inception_id,
                conversation_id=conversation_id,
                source_message_id=message_id,
                title="Restart",
                description="Restart",
                status="approved",
                trinity_assessment_json={},
            ),
            Mission(
                id=mission_id,
                inception_id=inception_id,
                creator_id=creator_id,
                title="Restart",
                objective="Recover",
                status="executing",
                authorization_json={"authorized_by": creator_id, "authorized_at": "2026-09-08T00:00:00Z"},
            ),
            MissionPlan(id=plan_id, mission_id=mission_id, strategy="recover", completion_criteria_json={}),
            MissionStep(
                id=step_id,
                plan_id=plan_id,
                step_key="recover",
                title="Recover",
                description="Recover",
                universe="engineering",
                position=1,
                depends_on_json=[],
                completion_criteria_json={},
                status="PENDING",
            ),
            Universe(id=universe_id, code="engineering", name="Engineering", active=True),
            Agent(id=agent_id, code="worker", name="Worker", universe_id=universe_id, active=True, capabilities_json={}),
            Task(
                id=task_id,
                mission_id=mission_id,
                step_id=step_id,
                universe_id=universe_id,
                agent_id=agent_id,
                status="RUNNING",
                input_json={},
                output_json={},
                error_json={},
                attempt_count=1,
                max_attempts=3,
                idempotency_key=f"{mission_id}:recover",
            ),
            AgentExecution(
                id=execution_id,
                task_id=task_id,
                agent_id=agent_id,
                attempt=1,
                status="RUNNING",
                input_json={},
                output_json={},
                error_json={},
            ),
        ])
        if invocation_id is not None:
            session.add(CapabilityInvocation(
                id=invocation_id,
                mission_id=mission_id,
                task_id=task_id,
                agent_execution_id=execution_id,
                capability="external",
                action="send",
                resource="resource",
                external_effect=True,
                idempotency_class="AT_MOST_ONCE",
                idempotency_key=str(uuid.uuid4()),
                authorization_version=1,
                status="AUTHORIZED",
                request_json={},
                result_json={},
                error_json={},
            ))
        await session.commit()
    return task_id, execution_id, invocation_id


@pytest.mark.asyncio
async def test_restart_retries_interrupted_retryable_execution(database):
    task_id, execution_id, _ = await running_attempt(database, at_most_once=False)
    counts = await ExecutionReconciler(database).reconcile(str(uuid.uuid4()))
    assert counts["retried_tasks"] == 1

    async with database() as session:
        task = await session.get(Task, task_id)
        execution = await session.get(AgentExecution, execution_id)
        assert task is not None and task.status == "READY"
        assert execution is not None and execution.status == "FAILED"
        assert execution.error_json["code"] == "INTERRUPTED_BY_RESTART"


@pytest.mark.asyncio
async def test_restart_never_replays_uncertain_at_most_once_effect(database):
    task_id, _, invocation_id = await running_attempt(database, at_most_once=True)
    counts = await ExecutionReconciler(database).reconcile(str(uuid.uuid4()))
    assert counts["blocked_tasks"] == 1
    assert counts["uncertain_capabilities"] == 1

    async with database() as session:
        task = await session.get(Task, task_id)
        invocation = await session.get(CapabilityInvocation, invocation_id)
        assert task is not None and task.status == "BLOCKED"
        assert task.error_json["code"] == "AT_MOST_ONCE_RECONCILIATION_REQUIRED"
        assert invocation is not None and invocation.status == "UNCERTAIN"
