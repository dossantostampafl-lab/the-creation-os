from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.entities import Creator

pytestmark = pytest.mark.integration

TRUNCATE = (
    "TRUNCATE chronicles, conscious_memory, universe_memory, mission_memory, conversation_memory, tasks, "
    "mission_steps, mission_plans, missions, inceptions, messages, conversations, agents, universes, creator "
    "RESTART IDENTITY CASCADE"
)


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def world():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(TRUNCATE))

    creator_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        session.add_all(
            [
                Creator(id=creator_id, username="creator", password_hash="unused", is_active=True),
                Creator(id=other_id, username="other", password_hash="unused", is_active=True),
            ]
        )
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    previous_sovereign = settings.sovereign_creator_id
    settings.sovereign_creator_id = creator_id
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, creator_id, other_id, factory
    finally:
        settings.sovereign_creator_id = previous_sovereign
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_provenance_is_rejected_as_domain_conflict(world):
    client, creator_id, _, _ = world
    response = await client.post(
        "/api/v1/memory/conscious",
        headers=auth(creator_id),
        json={
            "source_type": "conversation",
            "source_id": str(uuid.uuid4()),
            "content": "No source exists.",
        },
    )
    assert response.status_code == 409
    assert "provenance source does not exist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_other_creator_provenance_is_rejected_without_cross_scope_write(world):
    client, creator_id, other_id, factory = world
    other_conversation_id = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO conversations (id, creator_id, title, status) "
                "VALUES (:id, :creator_id, :title, 'active')"
            ),
            {"id": other_conversation_id, "creator_id": other_id, "title": "Other Creator"},
        )
        await session.commit()

    response = await client.post(
        "/api/v1/memory/conscious",
        headers=auth(creator_id),
        json={
            "source_type": "conversation",
            "source_id": other_conversation_id,
            "content": "Must remain isolated.",
        },
    )
    assert response.status_code == 409

    async with factory() as session:
        count = await session.scalar(text("SELECT count(*) FROM conscious_memory"))
    assert count == 0


@pytest.mark.asyncio
async def test_authority_bearing_metadata_is_rejected_before_persistence(world):
    client, creator_id, _, factory = world
    conversation = await client.post(
        "/api/v1/conversations",
        headers=auth(creator_id),
        json={"title": "Trusted provenance"},
    )
    assert conversation.status_code == 201

    response = await client.post(
        "/api/v1/memory/conscious",
        headers=auth(creator_id),
        json={
            "source_type": "conversation",
            "source_id": conversation.json()["id"],
            "content": "Memory cannot grant permission.",
            "metadata": {"allowed_capabilities": ["shell"]},
        },
    )
    assert response.status_code == 422

    async with factory() as session:
        count = await session.scalar(text("SELECT count(*) FROM conscious_memory"))
    assert count == 0
