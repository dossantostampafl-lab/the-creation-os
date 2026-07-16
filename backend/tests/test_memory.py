from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.memory import service as memory_api_service
from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor, AuthorizationDenied
from app.core.memory import MemoryType, build_memory_document, normalize_memory_text
from app.main import app
from app.models.memory import CreatorMemory
from app.schemas.auth import TokenPayload
from app.services.memory import MemoryError, MemoryService


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, CreatorMemory] = {}
        self.events: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    async def by_fingerprint(self, fingerprint: str) -> CreatorMemory | None:
        return self.items.get(fingerprint)

    async def add(self, item: CreatorMemory) -> CreatorMemory:
        item.id = item.id or "memory-1"
        self.items[item.memory_fingerprint] = item
        return item

    async def search(
        self,
        *,
        creator_id: str,
        query: str | None = None,
        memory_type: str | None = None,
        memory_types: list[str] | None = None,
        min_importance: int = 1,
        limit: int = 20,
    ):
        values = [item for item in self.items.values() if item.creator_id == creator_id]
        if memory_type is not None:
            values = [item for item in values if item.memory_type == memory_type]
        if memory_types is not None:
            values = [item for item in values if item.memory_type in memory_types]
        values = [item for item in values if item.importance >= min_importance]
        if query is not None:
            values = [item for item in values if query in item.normalized_content or query in item.source.lower()]
        return values[:limit]

    async def add_event(self, aggregate_id: str, actor_id: str, actor_role: str, correlation_id: str, payload: dict) -> None:
        self.events.append(
            {
                "aggregate_id": aggregate_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "correlation_id": correlation_id,
                "payload": payload,
            }
        )

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_memory_document_is_deterministic_and_canonical():
    first = build_memory_document(
        creator_id="creator-1",
        memory_type=MemoryType.CREATOR,
        content="  Preferência: responder em Português. ",
        source="creator_rule",
        importance=9,
        metadata={"approved": True},
    )
    second = build_memory_document(
        creator_id="creator-1",
        memory_type="CREATOR",
        content="preferencia: responder em portugues.",
        source="creator_rule",
        importance=9,
        metadata={"approved": True},
    )

    assert first.normalized_content == "preferencia: responder em portugues."
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


def test_memory_types_are_limited_to_four_allowed_categories():
    assert [item.value for item in MemoryType] == ["EPISODIC", "SEMANTIC", "OPERATIONAL", "CREATOR"]
    with pytest.raises(ValueError):
        build_memory_document(
            creator_id="creator-1",
            memory_type="PROBABILISTIC",
            content="invalid",
            source="test",
            importance=1,
        )


@pytest.mark.asyncio
async def test_memory_service_records_auditable_creator_scoped_memory_idempotently():
    repository = FakeMemoryRepository()
    service = MemoryService(repository)  # type: ignore[arg-type]
    actor = Actor(id="creator-1", role="creator")

    created, was_created = await service.remember(
        actor,
        memory_type="SEMANTIC",
        content="Central Core valida decisões técnicas.",
        source="approved_knowledge",
        importance=7,
        metadata={"origin": "test"},
        correlation_id="correlation-1",
    )
    replayed, replay_created = await service.remember(
        actor,
        memory_type="SEMANTIC",
        content="central core valida decisoes tecnicas.",
        source="approved_knowledge",
        importance=7,
        metadata={"origin": "test"},
        correlation_id="correlation-2",
    )

    assert was_created is True
    assert replay_created is False
    assert replayed.memory_fingerprint == created.memory_fingerprint
    assert len(repository.items) == 1
    assert len(repository.events) == 1
    assert repository.events[0]["payload"]["memory_type"] == "SEMANTIC"


@pytest.mark.asyncio
async def test_memory_search_is_creator_scoped_and_contextual():
    repository = FakeMemoryRepository()
    service = MemoryService(repository)  # type: ignore[arg-type]
    actor = Actor(id="creator-1", role="creator")
    other = Actor(id="creator-2", role="creator")

    await service.remember(
        actor,
        memory_type="OPERATIONAL",
        content="Decisão aprovada não cria missão automaticamente.",
        source="decision_policy",
        importance=8,
        metadata={},
        correlation_id="correlation-1",
    )
    await service.remember(
        other,
        memory_type="OPERATIONAL",
        content="Registro de outro Criador.",
        source="decision_policy",
        importance=8,
        metadata={},
        correlation_id="correlation-2",
    )

    results = await service.search(actor, query="missao", memory_type="OPERATIONAL", limit=10)

    assert len(results) == 1
    assert results[0].creator_id == "creator-1"


@pytest.mark.asyncio
async def test_memory_service_rejects_non_creator_and_invalid_importance():
    service = MemoryService(FakeMemoryRepository())  # type: ignore[arg-type]

    with pytest.raises(AuthorizationDenied):
        await service.search(Actor(id="agent-1", role="agent"), query=None, memory_type=None, limit=10)

    with pytest.raises(MemoryError):
        await service.remember(
            Actor(id="creator-1", role="creator"),
            memory_type="EPISODIC",
            content="evento",
            source="conversation",
            importance=11,
            metadata={},
            correlation_id="correlation-1",
        )


def test_normalize_memory_text_supports_contextual_search():
    assert normalize_memory_text(" Missão   APROVADA ") == "missao aprovada"


class FakeApiMemoryService:
    def __init__(self) -> None:
        self.item = SimpleMemory(
            id="memory-1",
            creator_id="creator-1",
            memory_type="CREATOR",
            source="creator_rule",
            content="Responder em português.",
            importance=9,
            metadata_json={"approved": True},
            memory_fingerprint="f" * 64,
            created_at=datetime.now(timezone.utc),
        )

    async def remember(self, actor: Actor, **kwargs):
        assert actor.id == "creator-1"
        return self.item, True

    async def search(self, actor: Actor, **kwargs):
        assert actor.id == "creator-1"
        return [self.item]


class SimpleMemory:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


@pytest.mark.asyncio
async def test_memory_api_records_memory_without_real_database():
    fake_service = FakeApiMemoryService()
    app.dependency_overrides[get_sovereign_creator] = lambda: TokenPayload(
        sub="creator-1",
        type="access",
        jti=str(uuid.uuid4()),
        exp=9999999999,
    )
    app.dependency_overrides[memory_api_service] = lambda: fake_service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/memory",
                json={
                    "memory_type": "CREATOR",
                    "content": "Responder em português.",
                    "source": "creator_rule",
                    "importance": 9,
                    "metadata": {"approved": True},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["memory_type"] == "CREATOR"
    assert response.json()["memory_fingerprint"] == "f" * 64


@pytest.mark.asyncio
async def test_memory_api_search_never_creates_data():
    fake_service = FakeApiMemoryService()
    app.dependency_overrides[get_sovereign_creator] = lambda: TokenPayload(
        sub="creator-1",
        type="access",
        jti=str(uuid.uuid4()),
        exp=9999999999,
    )
    app.dependency_overrides[memory_api_service] = lambda: fake_service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/memory/search?q=portugues&memory_type=CREATOR")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
