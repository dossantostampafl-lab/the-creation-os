from __future__ import annotations

import asyncio
import copy
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from db_safety import create_isolated_test_engine, validated_test_database_url
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.core.consolidation import ConsolidationError
from app.db.session import get_session
from app.main import app
from app.models.consolidation import MissionConsolidation
from app.models.dispatch import DispatchItem, Worker
from app.models.entities import (
    Agent,
    AgentCapability,
    Capability,
    Conversation,
    Creator,
    Inception,
    Message,
    Mission,
    Task,
    TaskDependency,
)
from app.models.execution import AgentExecution
from app.repositories.consolidation import ConsolidationRepository
from app.services.consolidation import ConsolidationService

pytestmark = pytest.mark.integration


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_0009_migration_round_trip():
    project = Path(__file__).resolve().parents[1]
    database_url = validated_test_database_url()
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0008_agent_execution"],
        cwd=project,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT to_regclass('public.mission_consolidations')")) is None
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0008_agent_execution"
    await engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0009_tree_core_consolidation"],
        cwd=project,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT to_regclass('public.mission_consolidations')")) == "mission_consolidations"
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009_tree_core_consolidation"
    await engine.dispose()


@pytest.fixture
async def consolidation_db(request):
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE mission_consolidations, agent_execution_events, agent_executions, "
                "worker_capabilities, workers, dispatch_attempts, dispatch_items, task_dependencies, tasks, "
                "agent_capabilities, capabilities, agents, universes, chronicles, mission_plans, missions, "
                "inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )

    ids = {
        key: str(uuid.uuid4())
        for key in (
            "creator",
            "conversation",
            "message",
            "inception",
            "mission",
            "capability",
            "agent",
            "worker",
            "worker_uuid",
            "task1",
            "task2",
            "dispatch1",
            "dispatch2",
            "execution1",
            "execution2",
        )
    }
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(Creator(id=ids["creator"], username="creator", password_hash="unused", is_active=True))
        await session.commit()
        session.add(Conversation(id=ids["conversation"], creator_id=ids["creator"], title="consolidation", status="active"))
        await session.commit()
        session.add(
            Message(
                id=ids["message"],
                conversation_id=ids["conversation"],
                role="creator",
                actor_id=ids["creator"],
                correlation_id=str(uuid.uuid4()),
                content="consolidate",
                route="central",
                metadata_json={},
            )
        )
        await session.commit()
        session.add(
            Inception(
                id=ids["inception"],
                conversation_id=ids["conversation"],
                source_message_id=ids["message"],
                title="Consolidation",
                description="Tree Core consolidation",
                status="approved",
                trinity_assessment_json={},
            )
        )
        await session.commit()
        session.add(
            Mission(
                id=ids["mission"],
                inception_id=ids["inception"],
                creator_id=ids["creator"],
                title="Mission",
                objective="Consolidate deterministic results",
                status="authorized",
                authorization_json={},
            )
        )
        await session.commit()
        session.add(Capability(id=ids["capability"], name="planning", description=""))
        session.add(
            Agent(
                id=ids["agent"],
                name="agent",
                description="",
                universe_name="central",
                active=True,
                capabilities_json={},
                priority=1,
                status="idle",
                version=1,
                heartbeat_at=now,
                enabled=True,
            )
        )
        session.add(
            Worker(
                id=ids["worker"],
                worker_uuid=ids["worker_uuid"],
                worker_name="worker",
                version="1.0",
                credential_hash="0" * 64,
                status="available",
                last_heartbeat=now,
            )
        )
        await session.commit()
        session.add(AgentCapability(agent_id=ids["agent"], capability_id=ids["capability"]))
        for task_id, name in ((ids["task1"], "First"), (ids["task2"], "Second")):
            session.add(
                Task(
                    id=task_id,
                    mission_id=ids["mission"],
                    name=name,
                    description=name,
                    required_capability_id=ids["capability"],
                    priority=1,
                    state="ready",
                    retry_limit=3,
                    retry_count=0,
                    timeout_seconds=30,
                    status="PENDING",
                    input_json={},
                    output_json={},
                    error_json={},
                    attempt_count=0,
                    max_attempts=3,
                    idempotency_key=str(uuid.uuid4()),
                )
            )
        await session.commit()
        session.add(TaskDependency(task_id=ids["task2"], dependency_id=ids["task1"]))
        incomplete_execution = request.node.name == "test_incomplete_execution_rolls_back_without_persistence"
        for index in (1, 2):
            is_incomplete = incomplete_execution and index == 2
            session.add(
                DispatchItem(
                    id=ids[f"dispatch{index}"],
                    task_id=ids[f"task{index}"],
                    mission_id=ids["mission"],
                    agent_id=ids["agent"],
                    capability_id=ids["capability"],
                    state="acknowledged",
                    priority=1,
                    available_at=now,
                    attempt_count=1,
                    max_attempts=3,
                    acknowledged_at=now,
                    version=1,
                )
            )
        await session.commit()
        for index in (1, 2):
            session.add(
                AgentExecution(
                    id=ids[f"execution{index}"],
                    dispatch_item_id=ids[f"dispatch{index}"],
                    mission_id=ids["mission"],
                    task_id=ids[f"task{index}"],
                    agent_id=ids["agent"],
                    worker_id=ids["worker"],
                    capability_id=ids["capability"],
                    attempt_number=1,
                    handler_name="structured_echo",
                    handler_version="1.0",
                    state="running" if is_incomplete else "succeeded",
                    input_payload={"index": index},
                    output_payload=None if is_incomplete else {"index": index, "value": f"result-{index}"},
                    result_metrics={"duration": index},
                    result_warnings=[],
                    contract_json={"schema": "object"},
                    deadline=now + timedelta(minutes=1),
                    max_duration_seconds=30,
                    started_at=now,
                    finished_at=None if is_incomplete else now,
                    version=1,
                )
            )
        await session.commit()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield factory, ids
    app.dependency_overrides.clear()
    await engine.dispose()


async def source_snapshot(factory, ids):
    async with factory() as session:
        mission = await session.get(Mission, ids["mission"])
        tasks = list((await session.scalars(select(Task).order_by(Task.id))).all())
        dispatches = list((await session.scalars(select(DispatchItem).order_by(DispatchItem.id))).all())
        executions = list((await session.scalars(select(AgentExecution).order_by(AgentExecution.id))).all())
        return copy.deepcopy(
            {
                "mission": (mission.id, mission.status, mission.version, mission.authorization_json),
                "tasks": [
                    (item.id, item.mission_id, item.state, item.status, item.output_json, item.updated_at) for item in tasks
                ],
                "dispatches": [
                    (item.id, item.mission_id, item.task_id, item.state, item.version, item.updated_at) for item in dispatches
                ],
                "executions": [
                    (
                        item.id,
                        item.mission_id,
                        item.task_id,
                        item.dispatch_item_id,
                        item.state,
                        item.output_payload,
                        item.version,
                        item.updated_at,
                    )
                    for item in executions
                ],
            }
        )


@pytest.mark.asyncio
async def test_http_creation_query_security_idempotency_and_source_immutability(consolidation_db):
    factory, ids = consolidation_db
    before = await source_snapshot(factory, ids)
    path = f"/api/v1/tree-core/missions/{ids['mission']}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"{path}/consolidate")).status_code == 401
        assert (await client.post(f"{path}/consolidate", headers=auth(str(uuid.uuid4())))).status_code == 403
        assert (await client.get(f"{path}/consolidation", headers=auth(ids["creator"]))).status_code == 404
        created = await client.post(f"{path}/consolidate", headers=auth(ids["creator"]))
        assert created.status_code == 201
        repeated = await client.post(f"{path}/consolidate", headers=auth(ids["creator"]))
        assert repeated.status_code == 200
        assert repeated.json() == created.json()
        queried = await client.get(f"{path}/consolidation", headers=auth(ids["creator"]))
        assert queried.status_code == 200 and queried.json() == created.json()
        assert queried.json()["status"] == "complete"
        assert queried.json()["completeness"]["complete"] is True
        assert [item["task_id"] for item in queried.json()["payload"]["tasks"]] == [ids["task1"], ids["task2"]]
        assert (await client.get("/api/v1/tree-core/missions/not-a-uuid/consolidation", headers=auth(ids["creator"]))).status_code == 422
        missing = str(uuid.uuid4())
        assert (await client.post(f"/api/v1/tree-core/missions/{missing}/consolidate", headers=auth(ids["creator"]))).status_code == 404

    assert await source_snapshot(factory, ids) == before
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 1


@pytest.mark.asyncio
async def test_real_postgresql_concurrency_and_unique_constraint(consolidation_db):
    factory, ids = consolidation_db

    async def consolidate_once():
        async with factory() as session:
            item, created = await ConsolidationService(ConsolidationRepository(session)).consolidate(ids["mission"])
            return item.id, created, item.fingerprint

    results = await asyncio.gather(consolidate_once(), consolidate_once())
    assert {item[1] for item in results} == {True, False}
    assert results[0][0] == results[1][0]
    assert results[0][2] == results[1][2]

    async with factory() as session:
        existing = await session.scalar(select(MissionConsolidation))
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 1
        session.add(
            MissionConsolidation(
                mission_id=ids["mission"],
                status="complete",
                payload_json=existing.payload_json,
                inconsistencies_json=[],
                completeness_json=existing.completeness_json,
                fingerprint=existing.fingerprint,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


class FailingCommitRepository(ConsolidationRepository):
    async def commit(self):
        await self.session.rollback()
        raise RuntimeError("forced commit failure")


@pytest.mark.asyncio
async def test_transaction_rollback_leaves_no_partial_consolidation(consolidation_db):
    factory, ids = consolidation_db
    before = await source_snapshot(factory, ids)
    async with factory() as session:
        with pytest.raises(RuntimeError, match="forced commit failure"):
            await ConsolidationService(FailingCommitRepository(session)).consolidate(ids["mission"])
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 0
    assert await source_snapshot(factory, ids) == before


@pytest.mark.asyncio
async def test_incomplete_execution_rolls_back_without_persistence(consolidation_db):
    factory, ids = consolidation_db
    async with factory() as session:
        with pytest.raises(ConsolidationError) as exc:
            await ConsolidationService(ConsolidationRepository(session)).consolidate(ids["mission"])
        assert "execution_not_terminal" in {item.code for item in exc.value.issues}
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 0
