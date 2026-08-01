from __future__ import annotations

import asyncio
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
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.core.domain import Actor
from app.db.session import get_session
from app.main import app
from app.models.entities import Chronicle, Conversation, Creator, Inception, Message, Mission
from app.models.execution import AgentExecution
from app.models.god import GodConversationInteraction
from app.models.manifestation import MissionManifestation
from app.models.rockmam import RockmamPossibilityAssessment
from app.models.sophia import SophiaUnderstanding
from app.repositories.rockmam import RockmamRepository
from app.services.rockmam import RockmamService

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
    return {"Authorization": f"Bearer {token}", "X-Correlation-ID": str(uuid.uuid4())}


def run_alembic(revision: str, operation: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = validated_test_database_url()
    subprocess.run(
        [sys.executable, "-m", "alembic", operation, revision],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        text=True,
    )


@pytest.fixture
async def rockmam_database():
    run_alembic("0015_rockmam_assessment", "upgrade")
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE chronicles, rockmam_possibility_assessments, sophia_understandings, "
                "god_conversation_interactions, mission_manifestations, mission_decision_reasoning, "
                "mission_decisions, mission_consolidations, agent_executions, mission_plans, missions, "
                "inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    understanding_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
    async with factory() as session:
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="ROCKMAM", status="active"))
        await session.commit()
    async with factory() as session:
        creator_message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            actor_id=creator_id,
            role="creator",
            correlation_id=str(uuid.uuid4()),
            content="Criar sistema",
            route="god",
            metadata_json={"idempotency_key": "source-key"},
        )
        god_message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            actor_id="god",
            role="god",
            correlation_id=str(uuid.uuid4()),
            content="Potencial identificado.",
            route="god",
            metadata_json={"interaction_type": "POTENTIAL"},
        )
        session.add_all([creator_message, god_message])
        await session.flush()
        god = GodConversationInteraction(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            creator_message_id=creator_message.id,
            god_message_id=god_message.id,
            idempotency_key="source-key",
            interaction_type="POTENTIAL",
            request_payload={
                "message": "Criar sistema",
                "idempotency_key": "source-key",
                "policy_version": "v0.7.0",
                "request_fingerprint": "a" * 64,
            },
            response_payload={
                "conversation_id": conversation_id,
                "message_id": creator_message.id,
                "god_message_id": god_message.id,
                "interaction_type": "POTENTIAL",
                "reply": {"message": "Potencial identificado.", "policy_version": "v0.7.0"},
                "potential_detected": True,
                "next_action": "creator_may_request_trinity_analysis",
                "fingerprint": "b" * 64,
            },
            potential_detected=True,
            fingerprint="b" * 64,
        )
        session.add(god)
        await session.flush()
        session.add(
            SophiaUnderstanding(
                id=understanding_id,
                god_interaction_id=god.id,
                conversation_id=conversation_id,
                understanding_type="POTENTIAL_UNDERSTANDING",
                understanding_payload={
                    "schema_version": "1.0",
                    "understanding_version": "v0.8.0",
                    "source": "DEUS",
                    "god_interaction_id": god.id,
                    "conversation_id": conversation_id,
                    "interaction_type": "POTENTIAL",
                    "understanding_type": "POTENTIAL_UNDERSTANDING",
                    "normalized_message": "criar sistema",
                    "potential_detected": True,
                    "boundaries": {
                        "decides": False,
                        "manifests": False,
                        "executes": False,
                        "creates_inception": False,
                        "creates_mission": False,
                    },
                    "signals": {
                        "direct_response": False,
                        "informational": False,
                        "potential": True,
                        "unsupported": False,
                    },
                },
                source_fingerprint="c" * 64,
                understanding_fingerprint="d" * 64,
            )
        )
        await session.commit()

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    yield factory, {"creator": creator_id, "conversation": conversation_id, "understanding": understanding_id}
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_0015_migration_round_trip_constraints_and_triggers():
    run_alembic("0015_rockmam_assessment", "upgrade")
    run_alembic("0014_sophia_understanding", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014_sophia_understanding"
        assert await connection.scalar(text("SELECT to_regclass('public.rockmam_possibility_assessments')")) is None
    await engine.dispose()

    run_alembic("0015_rockmam_assessment", "upgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0015_rockmam_assessment"
        assert await connection.scalar(
            text("SELECT to_regclass('public.rockmam_possibility_assessments')")
        ) == "rockmam_possibility_assessments"
        constraints = set(
            (
                await connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid='rockmam_possibility_assessments'::regclass"
                    )
                )
            ).all()
        )
        assert constraints >= {
            "rockmam_possibility_assessments_pkey",
            "rockmam_possibility_assessments_sophia_understanding_id_fkey",
            "rockmam_possibility_assessments_conversation_id_fkey",
            "uq_rockmam_assessment_sophia_understanding",
            "ck_rockmam_assessment_result",
            "ck_rockmam_source_fingerprint",
            "ck_rockmam_assessment_fingerprint",
        }
        assert await connection.scalar(
            text("SELECT count(*) FROM pg_trigger WHERE tgname='trg_rockmam_assessment_immutable' AND NOT tgisinternal")
        ) == 1
    await engine.dispose()

    run_alembic("0014_sophia_understanding", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014_sophia_understanding"
        assert await connection.scalar(text("SELECT to_regclass('public.rockmam_possibility_assessments')")) is None
    await engine.dispose()
    run_alembic("0015_rockmam_assessment", "upgrade")


@pytest.mark.asyncio
async def test_http_rockmam_assessment_idempotent_and_non_creating(rockmam_database):
    factory, ids = rockmam_database
    path = f"/api/v1/rockmam/sophia-understandings/{ids['understanding']}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"{path}/assess")).status_code == 401
        created = await client.post(f"{path}/assess", headers=auth(ids["creator"]))
        assert created.status_code == 201
        payload = created.json()
        assert payload["sophia_understanding_id"] == ids["understanding"]
        assert payload["assessment_result"] == "REQUIRES_CREATOR"
        assert payload["assessment_payload"]["technical_viability"] is True
        assert payload["assessment_payload"]["capabilities"]["external_execution_available"] is False
        repeated = await client.post(f"{path}/assess", headers=auth(ids["creator"]))
        assert repeated.status_code == 200
        assert repeated.json() == payload
        queried = await client.get(f"{path}/assessment", headers=auth(ids["creator"]))
        assert queried.status_code == 200
        assert queried.json() == payload

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RockmamPossibilityAssessment)) == 1
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 1
        assert await session.scalar(select(func.count()).select_from(Inception)) == 0
        assert await session.scalar(select(func.count()).select_from(Mission)) == 0
        assert await session.scalar(select(func.count()).select_from(AgentExecution)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionManifestation)) == 0


@pytest.mark.asyncio
async def test_missing_understanding_and_get_without_creation(rockmam_database):
    factory, ids = rockmam_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (
            await client.post(f"/api/v1/rockmam/sophia-understandings/{uuid.uuid4()}/assess", headers=auth(ids["creator"]))
        ).status_code == 404
        assert (
            await client.get(
                f"/api/v1/rockmam/sophia-understandings/{ids['understanding']}/assessment",
                headers=auth(ids["creator"]),
            )
        ).status_code == 404

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RockmamPossibilityAssessment)) == 0
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 0


@pytest.mark.asyncio
async def test_concurrent_assessment_creates_one_row(rockmam_database):
    factory, ids = rockmam_database

    async def assess_once():
        async with factory() as session:
            return await RockmamService(RockmamRepository(session)).assess(
                Actor(ids["creator"], "creator"),
                ids["understanding"],
                str(uuid.uuid4()),
            )

    results = await asyncio.gather(assess_once(), assess_once())
    assert {created for _, created in results} == {True, False}
    assert results[0][0].id == results[1][0].id
    assert results[0][0].assessment_fingerprint == results[1][0].assessment_fingerprint

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RockmamPossibilityAssessment)) == 1
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 1


class FailingRockmamRepository(RockmamRepository):
    async def add_event(self, *args, **kwargs) -> None:
        raise RuntimeError("forced rockmam audit failure")


@pytest.mark.asyncio
async def test_rollback_leaves_no_partial_rockmam_persistence(rockmam_database):
    factory, ids = rockmam_database
    async with factory() as session:
        with pytest.raises(RuntimeError):
            await RockmamService(FailingRockmamRepository(session)).assess(
                Actor(ids["creator"], "creator"),
                ids["understanding"],
                str(uuid.uuid4()),
            )
        await session.rollback()

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RockmamPossibilityAssessment)) == 0
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 0


@pytest.mark.asyncio
async def test_rockmam_assessment_is_immutable(rockmam_database):
    factory, ids = rockmam_database
    async with factory() as session:
        item, _ = await RockmamService(RockmamRepository(session)).assess(
            Actor(ids["creator"], "creator"),
            ids["understanding"],
            str(uuid.uuid4()),
        )

    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE rockmam_possibility_assessments SET assessment_result='VIABLE' WHERE id=:id"),
                {"id": item.id},
            )
            await session.commit()
        await session.rollback()
