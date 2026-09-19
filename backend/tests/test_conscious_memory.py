from __future__ import annotations

import uuid

import pytest
from db_safety import create_isolated_test_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.fake import FakeEmbeddingModel
from app.core.domain import Actor, AuthorizationDenied
from app.repositories.conscious_memory import ConsciousMemoryRepository
from app.services.conscious_memory import ConsciousMemoryError, ConsciousMemoryService

pytestmark = pytest.mark.integration


@pytest.fixture
async def conscious_memory_db():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE conscious_memory RESTART IDENTITY CASCADE"))
    yield factory
    await engine.dispose()


def creator() -> Actor:
    return Actor(id=str(uuid.uuid4()), role="creator")


def other_role() -> Actor:
    return Actor(id=str(uuid.uuid4()), role="user")


@pytest.mark.asyncio
async def test_explicit_consolidation_requires_creator_and_persists(conscious_memory_db):
    factory = conscious_memory_db
    async with factory() as session:
        service = ConsciousMemoryService(ConsciousMemoryRepository(session))

        with pytest.raises(AuthorizationDenied):
            await service.consolidate_explicit(
                other_role(), source_type="test", source_id="s1", content="not allowed", correlation_id=str(uuid.uuid4())
            )

        actor = creator()
        item = await service.consolidate_explicit(
            actor,
            source_type="creator_decision",
            source_id="s1",
            content="Trinity orchestration should retry once on transient failure.",
            metadata={"note": "policy"},
            correlation_id=str(uuid.uuid4()),
        )
        assert item.source_type == "creator_decision"
        assert item.metadata_json["trigger"] == "explicit_creator_decision"
        assert len(item.embedding) == 8

        fetched = await service.get(item.id)
        assert fetched is not None and fetched.content == item.content


@pytest.mark.asyncio
async def test_explicit_consolidation_rejects_empty_content(conscious_memory_db):
    factory = conscious_memory_db
    async with factory() as session:
        service = ConsciousMemoryService(ConsciousMemoryRepository(session))
        with pytest.raises(ConsciousMemoryError):
            await service.consolidate_explicit(
                creator(), source_type="test", source_id="s1", content="   ", correlation_id=str(uuid.uuid4())
            )


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_is_rejected(conscious_memory_db):
    factory = conscious_memory_db

    class WrongDimensionModel:
        async def embed(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3]  # not 8

    async with factory() as session:
        service = ConsciousMemoryService(ConsciousMemoryRepository(session), embedding_model=WrongDimensionModel())
        with pytest.raises(ConsciousMemoryError, match="dimension mismatch"):
            await service.consolidate_explicit(
                creator(), source_type="test", source_id="s1", content="bad dims", correlation_id=str(uuid.uuid4())
            )


@pytest.mark.asyncio
async def test_search_ranks_by_embedding_similarity_and_delete_works(conscious_memory_db):
    factory = conscious_memory_db
    actor = creator()
    async with factory() as session:
        service = ConsciousMemoryService(ConsciousMemoryRepository(session), embedding_model=FakeEmbeddingModel())
        close = await service.consolidate_explicit(
            actor, source_type="test", source_id="a", content="Trinity orchestration retry policy",
            correlation_id=str(uuid.uuid4()),
        )
        far = await service.consolidate_explicit(
            actor, source_type="test", source_id="b", content="Zzz completely unrelated topic entry",
            correlation_id=str(uuid.uuid4()),
        )

        results = await service.search("Trinity orchestration insight", limit=5)
        assert results[0].id == close.id
        assert far.id in {item.id for item in results}  # both present, just ranked

        deleted = await service.delete(close.id, actor=actor, correlation_id=str(uuid.uuid4()))
        assert deleted is True
        assert await service.get(close.id) is None

        with pytest.raises(AuthorizationDenied):
            await service.delete(far.id, actor=other_role(), correlation_id=str(uuid.uuid4()))
