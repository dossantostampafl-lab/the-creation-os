from __future__ import annotations

import uuid

import pytest
from db_safety import create_isolated_test_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.entities import (
    Conversation,
    ConversationMemory,
    Creator,
    Inception,
    Message,
    Mission,
    MissionMemory,
    Universe,
    UniverseMemory,
)
from app.repositories.scoped_memory import ScopedMemoryRepository
from app.services.scoped_memory import ScopedMemoryError, ScopedMemoryService

pytestmark = pytest.mark.integration


@pytest.fixture
async def scoped_memory_db():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE conversation_memory, mission_memory, universe_memory, tasks, missions, inceptions, "
                "messages, conversations, universes, creator RESTART IDENTITY CASCADE"
            )
        )
    ids = {key: str(uuid.uuid4()) for key in ("creator", "conversation", "message", "inception", "mission", "universe")}
    async with factory() as session:
        session.add(Creator(id=ids["creator"], username="creator", password_hash="unused", is_active=True))
        await session.commit()
        session.add(Conversation(id=ids["conversation"], creator_id=ids["creator"], title="mem", status="active"))
        await session.commit()
        session.add(
            Message(
                id=ids["message"], conversation_id=ids["conversation"], role="creator", actor_id=ids["creator"],
                correlation_id=str(uuid.uuid4()), content="x", route="central", metadata_json={},
            )
        )
        await session.commit()
        session.add(
            Inception(
                id=ids["inception"], conversation_id=ids["conversation"], source_message_id=ids["message"],
                title="Memory", description="scoped memory test", status="approved", trinity_assessment_json={},
            )
        )
        await session.commit()
        session.add(
            Mission(
                id=ids["mission"], inception_id=ids["inception"], creator_id=ids["creator"], title="Mission",
                objective="test", status="drafted", authorization_json={},
            )
        )
        session.add(Universe(id=ids["universe"], code="knowledge", name="Conhecimento", active=True))
        await session.commit()
    yield factory, ids
    await engine.dispose()


@pytest.mark.asyncio
async def test_conversation_memory_get_set_search_delete(scoped_memory_db):
    factory, ids = scoped_memory_db
    async with factory() as session:
        repository = ScopedMemoryRepository(session, ConversationMemory, "conversation_id", ids["conversation"])
        service = ScopedMemoryService(repository, aggregate_type="conversation_memory", actor_id=ids["creator"], actor_role="creator")

        assert await service.get("last_topic") is None

        created = await service.set("last_topic", {"topic": "Trinity"}, correlation_id=str(uuid.uuid4()))
        assert created.value_json == {"topic": "Trinity"}

        fetched = await service.get("last_topic")
        assert fetched is not None and fetched.value_json == {"topic": "Trinity"}

        updated = await service.set("last_topic", {"topic": "Malkuth"}, correlation_id=str(uuid.uuid4()))
        assert updated.id == created.id  # upsert, not a duplicate row
        assert updated.value_json == {"topic": "Malkuth"}

        results = await service.search("last", limit=10)
        assert [item.key for item in results] == ["last_topic"]

        deleted = await service.delete("last_topic", correlation_id=str(uuid.uuid4()))
        assert deleted is True
        assert await service.get("last_topic") is None
        assert await service.delete("last_topic", correlation_id=str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_set_rejects_empty_key(scoped_memory_db):
    factory, ids = scoped_memory_db
    async with factory() as session:
        repository = ScopedMemoryRepository(session, ConversationMemory, "conversation_id", ids["conversation"])
        service = ScopedMemoryService(repository, aggregate_type="conversation_memory", actor_id=ids["creator"], actor_role="creator")
        with pytest.raises(ScopedMemoryError):
            await service.set("  ", {}, correlation_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_mission_and_universe_memory_use_the_same_generic_repository(scoped_memory_db):
    """The three operational layers (conversation/mission/universe) share one
    repository/service implementation — this proves it actually works for the
    other two parent scopes, not just conversation_memory."""
    factory, ids = scoped_memory_db
    async with factory() as session:
        mission_repo = ScopedMemoryRepository(session, MissionMemory, "mission_id", ids["mission"])
        mission_service = ScopedMemoryService(mission_repo, aggregate_type="mission_memory", actor_id=ids["creator"], actor_role="creator")
        await mission_service.set("focus", {"objective": "Ship RC1"}, correlation_id=str(uuid.uuid4()))
        assert (await mission_service.get("focus")).value_json == {"objective": "Ship RC1"}

        universe_repo = ScopedMemoryRepository(session, UniverseMemory, "universe_id", ids["universe"])
        universe_service = ScopedMemoryService(universe_repo, aggregate_type="universe_memory", actor_id=ids["creator"], actor_role="creator")
        await universe_service.set("agent_count", {"count": 1}, correlation_id=str(uuid.uuid4()))
        assert (await universe_service.get("agent_count")).value_json == {"count": 1}

        # Scopes never leak into each other despite sharing the same key.
        assert await mission_service.get("agent_count") is None
        assert await universe_service.get("focus") is None
