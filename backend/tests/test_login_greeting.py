"""Lote: DEUS inicia conversa automaticamente após login. Confirms POST
/auth/login persists a real, contextual GOD greeting into the Creator's
anchor conversation, that it is idempotent within the cooldown window, that
it fires again once the window has passed, that GET /auth/refresh never
triggers it, and that the new GET /conversations/{id}/messages route (added
because the audit found no such endpoint already existed) exposes it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import app
from app.models.entities import Conversation, Inception, Message, Mission

pytestmark = pytest.mark.integration


@pytest.fixture
async def empty_creator_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE creator RESTART IDENTITY CASCADE"))

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
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def _seed_running_mission_and_pending_inception(factory, creator_id: str) -> None:
    async with factory() as session:
        conversation = Conversation(creator_id=creator_id, title="seed", status="active")
        session.add(conversation)
        await session.flush()
        message = Message(
            conversation_id=conversation.id, actor_id=creator_id, role="creator", content="seed",
            route="central", correlation_id=str(uuid.uuid4()), metadata_json={},
        )
        session.add(message)
        await session.flush()
        inception = Inception(
            conversation_id=conversation.id, source_message_id=message.id, title="seed inception",
            description="d", status="proposed", trinity_assessment_json={},
        )
        session.add(inception)
        await session.flush()
        mission = Mission(
            inception_id=inception.id, creator_id=creator_id, title="seed mission", objective="o", status="authorized",
        )
        session.add(mission)
        await session.commit()


@pytest.mark.asyncio
async def test_login_generates_greeting_with_real_system_state(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bootstrap = await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})
        creator_id = bootstrap.json()["id"]
        await _seed_running_mission_and_pending_inception(empty_creator_database, creator_id)

        login = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        assert login.status_code == 200
        body = login.json()
        conversation_id = body["conversation_id"]
        assert conversation_id

        messages = await client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert messages.status_code == 200
        items = messages.json()
        assert len(items) == 1
        greeting = items[0]
        assert greeting["role"] == "god"
        assert greeting["metadata_json"]["greeting"] is True
        assert "1 missoes em andamento" in greeting["content"]
        assert "1 Inceptions pendentes" in greeting["content"]


@pytest.mark.asyncio
async def test_login_within_cooldown_does_not_repeat_greeting(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})

        first = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        conversation_id = first.json()["conversation_id"]
        access_token = first.json()["access_token"]

        second = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        assert second.status_code == 200
        assert second.json()["conversation_id"] == conversation_id

        messages = await client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers={"Authorization": f"Bearer {access_token}"}
        )
        assert len(messages.json()) == 1


@pytest.mark.asyncio
async def test_login_after_cooldown_expires_generates_new_greeting(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})

        first = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        conversation_id = first.json()["conversation_id"]

        stale = datetime.now(timezone.utc) - timedelta(minutes=31)
        async with empty_creator_database() as session:
            await session.execute(
                text("UPDATE messages SET created_at = :stale WHERE conversation_id = :cid"),
                {"stale": stale, "cid": conversation_id},
            )
            await session.commit()

        second = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        access_token = second.json()["access_token"]
        assert second.json()["conversation_id"] == conversation_id

        messages = await client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers={"Authorization": f"Bearer {access_token}"}
        )
        items = messages.json()
        assert len(items) == 2
        assert all(item["metadata_json"]["greeting"] is True for item in items)


@pytest.mark.asyncio
async def test_refresh_does_not_generate_a_second_greeting(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})

        login = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        conversation_id = login.json()["conversation_id"]
        access_token = login.json()["access_token"]
        refresh_token = login.json()["refresh_token"]

        refreshed = await client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"})
        assert refreshed.status_code == 200
        assert refreshed.json()["conversation_id"] is None

        messages = await client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers={"Authorization": f"Bearer {access_token}"}
        )
        assert len(messages.json()) == 1


@pytest.mark.asyncio
async def test_conversation_messages_route_requires_authentication(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})
        login = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        conversation_id = login.json()["conversation_id"]

        unauthenticated = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert unauthenticated.status_code == 401

        missing = await client.get(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert missing.status_code == 404
