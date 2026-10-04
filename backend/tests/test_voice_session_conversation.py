from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.domain import ConversationStatus
from app.models.entities import Conversation, Message
from app.voice_session.conversation import VoiceConversationBridge


class FakeRepo:
    def __init__(self) -> None:
        self.conversation = SimpleNamespace(
            id="conversation-1",
            status=ConversationStatus.ACTIVE.value,
        )
        self.messages: list[Message] = []
        self.events: list[tuple[str, dict[str, object]]] = []
        self.commits = 0

    async def get(self, model, entity_id: str):
        if model is Conversation and entity_id == "conversation-1":
            return self.conversation
        return None

    async def owner_id(self, model, entity_id: str):
        return "creator-1" if model is Conversation and entity_id == "conversation-1" else None

    async def add(self, entity):
        if isinstance(entity, Message):
            if entity.id is None:
                entity.id = f"m-{len(self.messages) + 1}"
            self.messages.append(entity)
        return entity

    async def list_messages(self, conversation_id: str, limit: int = 20):
        assert conversation_id == "conversation-1"
        return self.messages[-limit:]

    async def add_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict[str, object],
    ):
        self.events.append((event_type, payload))

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_voice_bridge_persists_committed_creator_and_final_deus_reply():
    repo = FakeRepo()
    bridge = VoiceConversationBridge(
        repo,
        creator_id="creator-1",
        conversation_id="conversation-1",
    )
    await bridge.validate()

    request = await bridge.build_request("Como está o projeto?", 1)

    assert repo.messages[0].role == "creator"
    assert repo.messages[0].content == "Como está o projeto?"
    assert repo.commits == 1
    assert request.messages[0]["role"] == "system"
    assert request.messages[-1] == {"role": "user", "content": "Como está o projeto?"}

    await bridge.complete_turn(1, "Está operacional.", "freellmapi")

    assert [message.role for message in repo.messages] == ["creator", "deus"]
    assert repo.messages[-1].content == "Está operacional."
    assert repo.messages[-1].metadata_json["provider"] == "freellmapi"
    assert all(message.metadata_json["voice_session_id"] == bridge.session_id for message in repo.messages)
    assert repo.commits == 2
    assert repo.events[-1][0] == "deus_voice_response_generated"


@pytest.mark.asyncio
async def test_voice_bridge_rejects_conversation_owned_by_another_creator():
    repo = FakeRepo()

    async def wrong_owner(model, entity_id: str):
        return "creator-2"

    repo.owner_id = wrong_owner  # type: ignore[method-assign]
    bridge = VoiceConversationBridge(
        repo,
        creator_id="creator-1",
        conversation_id="conversation-1",
    )

    with pytest.raises(LookupError, match="Conversation not found"):
        await bridge.validate()
