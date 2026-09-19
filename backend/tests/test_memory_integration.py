"""Lote: fechar gap de POST /memory. Real-database proof that POST /memory
now writes conversation_memory (via the Creator's anchor Conversation,
CreatorRecallService) instead of the deprecated CreatorMemory, and that
GOD's memory recall — itself already reading conversation_memory since
Lote: Convergência de memória de conversa — genuinely sees what was
written through the HTTP route. No such end-to-end proof existed before
either lote; only fakes/mocks exercised this path previously.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.core.domain import Actor
from app.db.session import get_session
from app.main import app
from app.models.entities import Conversation, ConversationMemory, Creator
from app.repositories.god import GodConversationRepository
from app.services.god import GodConversationService

pytestmark = pytest.mark.integration


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def memory_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE conversation_memory, chronicles, god_conversation_interactions, messages, "
                "conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield factory, {"creator": creator_id}
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_post_memory_writes_conversation_memory_not_creator_memory(memory_database):
    factory, ids = memory_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/memory",
            headers=auth(ids["creator"]),
            json={
                "memory_type": "CREATOR",
                "content": "Criador prefere respostas objetivas.",
                "source": "creator_rule",
                "importance": 9,
                "metadata": {"approved": True},
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["creator_id"] == ids["creator"]
    assert body["memory_type"] == "CREATOR"
    assert len(body["memory_fingerprint"]) == 64

    async with factory() as session:
        row_count = await session.scalar(select(func.count()).select_from(ConversationMemory))
        assert row_count == 1
        row = await session.scalar(select(ConversationMemory))
        assert row.value_json["content"] == "Criador prefere respostas objetivas."
        assert row.value_json["memory_fingerprint"] == body["memory_fingerprint"]
        assert row.key == body["memory_fingerprint"]
        # Written under a dedicated anchor Conversation belonging to the Creator.
        anchor = await session.get(Conversation, row.conversation_id)
        assert anchor.creator_id == ids["creator"]
        assert anchor.title == "__creator_memory__"


@pytest.mark.asyncio
async def test_post_memory_is_idempotent_by_fingerprint(memory_database):
    factory, ids = memory_database
    payload = {
        "memory_type": "SEMANTIC",
        "content": "Central Core valida decisões técnicas.",
        "source": "approved_knowledge",
        "importance": 7,
        "metadata": {},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/memory", headers=auth(ids["creator"]), json=payload)
        second = await client.post(
            "/api/v1/memory",
            headers=auth(ids["creator"]),
            json={**payload, "content": "central core valida decisoes tecnicas."},
        )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["memory_fingerprint"] == second.json()["memory_fingerprint"]

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ConversationMemory)) == 1


@pytest.mark.asyncio
async def test_get_memory_search_reads_back_what_post_memory_wrote(memory_database):
    factory, ids = memory_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/v1/memory",
            headers=auth(ids["creator"]),
            json={
                "memory_type": "OPERATIONAL",
                "content": "Decisão aprovada não cria missão automaticamente.",
                "source": "decision_policy",
                "importance": 8,
                "metadata": {},
            },
        )
        response = await client.get(
            "/api/v1/memory/search", headers=auth(ids["creator"]), params={"q": "missao", "memory_type": "OPERATIONAL"}
        )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["creator_id"] == ids["creator"]
    assert items[0]["content"] == "Decisão aprovada não cria missão automaticamente."


@pytest.mark.asyncio
async def test_god_memory_context_reflects_what_post_memory_wrote_end_to_end(memory_database):
    """The core proof this lote exists for: create via the real HTTP route,
    then have GOD interact — the content must appear in the memory context
    GOD actually used, with no manual DB seeding in between."""
    factory, ids = memory_database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/v1/memory",
            headers=auth(ids["creator"]),
            json={
                "memory_type": "CREATOR",
                "content": "Criador prefere respostas em portugues objetivo.",
                "source": "creator_rule",
                "importance": 9,
                "metadata": {},
            },
        )

    async with factory() as session:
        conversation_id = str(uuid.uuid4())
        session.add(Conversation(id=conversation_id, creator_id=ids["creator"], title="chat", status="active"))
        await session.commit()

    async with factory() as session:
        item, created = await GodConversationService(GodConversationRepository(session)).interact(
            Actor(ids["creator"], "creator"),
            conversation_id,
            "Nota: lembre sobre portugues",
            str(uuid.uuid4()),
            str(uuid.uuid4()),
        )

    assert created is True
    memory_context = item.response_payload["memory_context"]
    assert any("portugues" in entry["content"].lower() for entry in memory_context), memory_context
