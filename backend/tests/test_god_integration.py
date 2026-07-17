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
from app.main import app
from app.models.decision import MissionDecision
from app.models.entities import Chronicle, Conversation, Creator, Inception, Message
from app.models.execution import AgentExecution
from app.models.god import GodConversationInteraction
from app.models.manifestation import MissionManifestation
from app.repositories.god import GodConversationRepository
from app.services.god import GodConversationService, GodIdempotencyConflict

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
async def god_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE chronicles, god_conversation_interactions, mission_manifestations, "
                "mission_decision_reasoning, mission_decisions, mission_consolidations, agent_executions, "
                "mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    async with factory() as session:
        session.add_all(
            [
                Creator(id=creator_id, username="creator", password_hash="unused", is_active=True),
                Creator(id=other_id, username="other", password_hash="unused", is_active=True),
            ]
        )
        await session.commit()
    async with factory() as session:
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="GOD", status="active"))
        await session.commit()

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides.clear()
    from app.db.session import get_session

    app.dependency_overrides[get_session] = override_session
    yield factory, {"creator": creator_id, "other": other_id, "conversation": conversation_id}
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_0013_migration_round_trip_constraints_and_triggers():
    run_alembic("0013_god_conversation", "upgrade")
    run_alembic("0012_malkuth_manifestation", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0012_malkuth_manifestation"
        assert await connection.scalar(text("SELECT to_regclass('public.god_conversation_interactions')")) is None
    await engine.dispose()

    run_alembic("0013_god_conversation", "upgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0013_god_conversation"
        assert await connection.scalar(
            text("SELECT to_regclass('public.god_conversation_interactions')")
        ) == "god_conversation_interactions"
        constraints = set(
            (
                await connection.scalars(
                    text("SELECT conname FROM pg_constraint WHERE conrelid='god_conversation_interactions'::regclass")
                )
            ).all()
        )
        assert constraints >= {
            "god_conversation_interactions_pkey",
            "god_conversation_interactions_conversation_id_fkey",
            "god_conversation_interactions_creator_message_id_fkey",
            "god_conversation_interactions_god_message_id_fkey",
            "uq_god_interaction_conversation_idempotency",
            "ck_god_interaction_type",
            "ck_god_interaction_fingerprint",
        }
        assert await connection.scalar(
            text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname='trg_god_conversation_interaction_immutable' AND NOT tgisinternal"
            )
        ) == 1
    await engine.dispose()

    run_alembic("0012_malkuth_manifestation", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0012_malkuth_manifestation"
        assert await connection.scalar(text("SELECT to_regclass('public.god_conversation_interactions')")) is None
    await engine.dispose()
    run_alembic("0013_god_conversation", "upgrade")


@pytest.mark.asyncio
async def test_http_god_contract_idempotency_auth_and_no_inception(god_database):
    factory, ids = god_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/living-core/conversations/{ids['conversation']}/god"
        body = {"message": "Quero criar um projeto interno", "idempotency_key": "god-key-1"}
        assert (await client.post(path, json=body)).status_code == 401
        assert (await client.post(path, headers=auth(ids["other"]), json=body)).status_code == 403

        created = await client.post(path, headers=auth(ids["creator"]), json=body)
        assert created.status_code == 201
        payload = created.json()
        assert payload["conversation_id"] == ids["conversation"]
        assert payload["interaction_type"] == "POTENTIAL"
        assert payload["potential_detected"] is True
        assert payload["next_action"] == "creator_may_request_trinity_analysis"
        assert len(payload["fingerprint"]) == 64

        repeated = await client.post(path, headers=auth(ids["creator"]), json=body)
        assert repeated.status_code == 200
        assert repeated.json() == payload

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(GodConversationInteraction)) == 1
        assert await session.scalar(select(func.count()).select_from(Message)) == 2
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 1
        assert await session.scalar(select(func.count()).select_from(Inception)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 0
        assert await session.scalar(select(func.count()).select_from(AgentExecution)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionManifestation)) == 0


@pytest.mark.asyncio
async def test_http_same_key_different_payload_conflicts_without_side_effects(god_database):
    factory, ids = god_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/living-core/conversations/{ids['conversation']}/god"
        created = await client.post(
            path,
            headers=auth(ids["creator"]),
            json={"message": "Criar projeto seguro", "idempotency_key": "conflict-key"},
        )
        assert created.status_code == 201
        original = created.json()

        conflict = await client.post(
            path,
            headers=auth(ids["creator"]),
            json={"message": "Chame Malkuth agora", "idempotency_key": "conflict-key"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "GodIdempotencyConflict"

    async with factory() as session:
        item = await session.scalar(select(GodConversationInteraction))
        assert item.id == original["id"]
        assert item.fingerprint == original["fingerprint"]
        assert item.request_payload["message"] == "Criar projeto seguro"
        assert await session.scalar(select(func.count()).select_from(GodConversationInteraction)) == 1
        assert await session.scalar(select(func.count()).select_from(Message)) == 2
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "interaction_type", "potential"),
    [
        ("Ola GOD", "DIRECT_RESPONSE", False),
        ("Nota para registro: contexto novo", "INFORMATIONAL", False),
        ("Criar um sistema", "POTENTIAL", True),
        ("Chame Malkuth para manifestar", "UNSUPPORTED", False),
    ],
)
async def test_service_interaction_types(god_database, message, interaction_type, potential):
    factory, ids = god_database
    async with factory() as session:
        item, created = await GodConversationService(GodConversationRepository(session)).interact(
            Actor(ids["creator"], "creator"),
            ids["conversation"],
            message,
            str(uuid.uuid4()),
            str(uuid.uuid4()),
        )
        assert created
        assert item.interaction_type == interaction_type
        assert item.potential_detected is potential


@pytest.mark.asyncio
async def test_missing_conversation_and_get_does_not_create(god_database):
    factory, ids = god_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post(
            f"/api/v1/living-core/conversations/{uuid.uuid4()}/god",
            headers=auth(ids["creator"]),
            json={"message": "Ola", "idempotency_key": "missing"},
        )
        assert missing.status_code == 404
        assert (await client.get(f"/api/v1/living-core/conversations/{ids['conversation']}/god")).status_code == 405

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(GodConversationInteraction)) == 0
        assert await session.scalar(select(func.count()).select_from(Message)) == 0


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_creates_one_interaction(god_database):
    factory, ids = god_database

    async def speak_once():
        async with factory() as session:
            return await GodConversationService(GodConversationRepository(session)).interact(
                Actor(ids["creator"], "creator"),
                ids["conversation"],
                "Criar projeto concorrente",
                "same-concurrent-key",
                str(uuid.uuid4()),
            )

    results = await asyncio.gather(speak_once(), speak_once())
    assert {created for _, created in results} == {True, False}
    assert results[0][0].id == results[1][0].id
    assert results[0][0].fingerprint == results[1][0].fingerprint

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(GodConversationInteraction)) == 1
        assert await session.scalar(select(func.count()).select_from(Message)) == 2


@pytest.mark.asyncio
async def test_concurrent_same_key_different_payloads_create_one_and_conflict(god_database):
    factory, ids = god_database

    async def speak_once(message: str):
        async with factory() as session:
            try:
                item, created = await GodConversationService(GodConversationRepository(session)).interact(
                    Actor(ids["creator"], "creator"),
                    ids["conversation"],
                    message,
                    "same-key-different-payload",
                    str(uuid.uuid4()),
                )
                return item.id, created, None
            except GodIdempotencyConflict as exc:
                await session.rollback()
                return None, False, exc.__class__.__name__

    results = await asyncio.gather(
        speak_once("Criar projeto concorrente"),
        speak_once("Chame Malkuth concorrente"),
    )
    assert {result[2] for result in results} == {None, "GodIdempotencyConflict"}
    assert sum(1 for result in results if result[0] is not None) == 1

    async with factory() as session:
        item = await session.scalar(select(GodConversationInteraction))
        assert item is not None
        assert item.request_payload["message"] in {"Criar projeto concorrente", "Chame Malkuth concorrente"}
        assert await session.scalar(select(func.count()).select_from(GodConversationInteraction)) == 1
        assert await session.scalar(select(func.count()).select_from(Message)) == 2
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 1


class FailingGodRepository(GodConversationRepository):
    async def add_event(self, *args, **kwargs) -> None:
        raise RuntimeError("forced audit failure")


@pytest.mark.asyncio
async def test_rollback_leaves_no_partial_god_persistence(god_database):
    factory, ids = god_database
    async with factory() as session:
        with pytest.raises(RuntimeError):
            await GodConversationService(FailingGodRepository(session)).interact(
                Actor(ids["creator"], "creator"),
                ids["conversation"],
                "Criar algo",
                "rollback-key",
                str(uuid.uuid4()),
            )
        await session.rollback()

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(GodConversationInteraction)) == 0
        assert await session.scalar(select(func.count()).select_from(Message)) == 0
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 0


@pytest.mark.asyncio
async def test_god_interaction_is_immutable(god_database):
    factory, ids = god_database
    async with factory() as session:
        item, _ = await GodConversationService(GodConversationRepository(session)).interact(
            Actor(ids["creator"], "creator"),
            ids["conversation"],
            "Ola",
            "immutable-key",
            str(uuid.uuid4()),
        )

    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE god_conversation_interactions SET interaction_type='INFORMATIONAL' WHERE id=:id"),
                {"id": item.id},
            )
            await session.commit()
        await session.rollback()
