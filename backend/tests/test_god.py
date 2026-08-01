from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.domain import Actor
from app.core.god import GodInteractionType, build_god_interaction, classify_message
from app.models.entities import Message
from app.models.god import GodConversationInteraction
from app.services.god import GodConversationService


def test_god_classification_is_deterministic_and_limited_to_contract():
    assert classify_message("Ola DEUS") == GodInteractionType.DIRECT_RESPONSE
    assert classify_message("Nota: lembre este contexto") == GodInteractionType.INFORMATIONAL
    assert classify_message("Quero criar um projeto novo") == GodInteractionType.POTENTIAL
    assert classify_message("Execute agent e chame Malkuth") == GodInteractionType.UNSUPPORTED


def test_god_interaction_fingerprint_is_deterministic():
    conversation_id = str(uuid.uuid4())
    first = build_god_interaction(conversation_id, "Criar sistema interno", "same-key")
    second = build_god_interaction(conversation_id, "  criar   sistema interno  ", "same-key")

    assert first == second
    assert first.interaction_type == GodInteractionType.POTENTIAL
    assert first.potential_detected
    assert first.next_action == "creator_may_request_trinity_analysis"
    assert len(first.request_fingerprint) == 64
    assert len(first.fingerprint) == 64


def test_god_interaction_fingerprint_audits_memory_context():
    conversation_id = str(uuid.uuid4())
    memory_context = [
        {
            "id": "memory-1",
            "memory_type": "CREATOR",
            "source": "creator_rule",
            "content": "Responder em portugues.",
            "importance": 9,
            "fingerprint": "a" * 64,
            "relevance_score": 94,
        }
    ]

    without_memory = build_god_interaction(conversation_id, "Criar sistema interno", "same-key")
    with_memory = build_god_interaction(conversation_id, "Criar sistema interno", "same-key", memory_context)

    assert without_memory.request_fingerprint == with_memory.request_fingerprint
    assert without_memory.fingerprint != with_memory.fingerprint


class FakeGodMemoryRepository:
    def __init__(self, memories: list[SimpleNamespace]) -> None:
        self.memories = memories

    async def search(self, **kwargs):
        assert kwargs["creator_id"] == "creator-1"
        assert kwargs["min_importance"] == 1
        return self.memories


class FakeGodRepository:
    def __init__(self) -> None:
        self.memory = FakeGodMemoryRepository(
            [
                SimpleNamespace(
                    id="memory-low",
                    memory_type="SEMANTIC",
                    source="knowledge",
                    content="Sistema legado",
                    normalized_content="sistema legado",
                    importance=3,
                    memory_fingerprint="b" * 64,
                ),
                SimpleNamespace(
                    id="memory-high",
                    memory_type="CREATOR",
                    source="creator_rule",
                    content="Criador prefere respostas objetivas sobre sistema interno.",
                    normalized_content="criador prefere respostas objetivas sobre sistema interno",
                    importance=9,
                    memory_fingerprint="a" * 64,
                ),
            ]
        )
        self.events: list[dict] = []
        self.messages: list[Message] = []
        self.interaction_item: GodConversationInteraction | None = None
        self.committed = False

    async def conversation(self, conversation_id: str, *, lock: bool = False):
        assert lock is True
        return SimpleNamespace(id=conversation_id, creator_id="creator-1", status="active")

    async def interaction(self, conversation_id: str, idempotency_key: str):
        return self.interaction_item

    async def add_message(self, item: Message) -> Message:
        item.id = str(uuid.uuid4())
        self.messages.append(item)
        return item

    async def add_interaction(self, item: GodConversationInteraction) -> GodConversationInteraction:
        item.id = str(uuid.uuid4())
        self.interaction_item = item
        return item

    async def add_event(self, event_type: str, aggregate_type: str, aggregate_id: str, actor_id: str, actor_role: str, correlation_id: str, payload: dict):
        self.events.append(payload)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        raise AssertionError("rollback should not be called")


@pytest.mark.asyncio
async def test_god_service_includes_deterministic_memory_context_without_creating_memory():
    repository = FakeGodRepository()
    service = GodConversationService(repository)  # type: ignore[arg-type]

    item, created = await service.interact(
        Actor(id="creator-1", role="creator"),
        str(uuid.uuid4()),
        "Criar sistema interno",
        "memory-key",
        str(uuid.uuid4()),
    )

    memory_context = item.response_payload["memory_context"]
    assert created is True
    assert [memory["id"] for memory in memory_context] == ["memory-high", "memory-low"]
    assert item.request_payload["memory_ids"] == ["memory-high", "memory-low"]
    assert repository.events[0]["memory_ids"] == ["memory-high", "memory-low"]
    assert repository.messages[1].metadata_json["memory_context"] == memory_context
    assert len(repository.memory.memories) == 2
    assert repository.committed is True
