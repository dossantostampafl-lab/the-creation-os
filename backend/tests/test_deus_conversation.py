from __future__ import annotations

import uuid

import pytest

from app.core.domain import Actor
from app.inference.contracts import InferenceRequest, InferenceResponse
from app.models.entities import Conversation, Message
from app.services.deus import DeusConversationService


class StubRouter:
    def __init__(self) -> None:
        self.requests: list[InferenceRequest] = []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        return InferenceResponse(provider="stub", model="stub-model", content="DEUS response")


class FakeRepository:
    def __init__(self, actor: Actor) -> None:
        self.actor = actor
        self.conversation = Conversation(
            id=str(uuid.uuid4()), creator_id=actor.id, title="Creator", status="active"
        )
        self.messages: list[Message] = []
        self.events: list[dict] = []
        self.commits = 0

    async def get(self, model, entity_id):
        if model is Conversation and entity_id == self.conversation.id:
            return self.conversation
        return None

    async def owner_id(self, model, entity_id):
        if model is Conversation and entity_id == self.conversation.id:
            return self.actor.id
        return None

    async def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = str(uuid.uuid4())
        if isinstance(entity, Message):
            self.messages.append(entity)
        return entity

    async def list_messages(self, conversation_id: str, limit: int = 20):
        return [message for message in self.messages if message.conversation_id == conversation_id][-limit:]

    async def add_event(self, event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id, payload=None):
        self.events.append({
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "correlation_id": correlation_id,
            "payload": payload or {},
        })

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_deus_uses_model_router_and_persists_both_sides_of_conversation() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    router = StubRouter()
    service = DeusConversationService(repo, router, provider="stub", model="stub-model")

    result = await service.respond(actor, repo.conversation.id, "What is our status?", str(uuid.uuid4()))

    assert result.response == "DEUS response"
    assert result.provider == "stub"
    assert [message.role for message in repo.messages] == ["creator", "deus"]
    assert repo.messages[0].content == "What is our status?"
    assert repo.messages[1].content == "DEUS response"
    assert router.requests[0].requirements.preferred_provider == "stub"
    assert router.requests[0].model == "stub-model"
    assert any(message["role"] == "system" and "DEUS" in message["content"] for message in router.requests[0].messages)
    assert repo.events[-1]["event_type"] == "deus_response_generated"
    assert repo.commits == 1


@pytest.mark.asyncio
async def test_deus_rejects_conversation_owned_by_another_creator() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    other = Actor(str(uuid.uuid4()), "creator")
    service = DeusConversationService(repo, StubRouter(), provider="stub", model="stub-model")

    with pytest.raises(Exception, match="Conversation not found"):
        await service.respond(other, repo.conversation.id, "hello", str(uuid.uuid4()))
