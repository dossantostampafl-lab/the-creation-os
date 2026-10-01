from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.domain import ConversationStatus
from app.inference.contracts import InferenceRequest
from app.models.entities import Conversation, Message
from app.repositories.domain import DomainRepository
from app.services.conversation_context import conversation_messages


@dataclass(frozen=True)
class PendingVoiceTurn:
    creator_message_id: str
    correlation_id: str


class VoiceConversationBridge:
    def __init__(
        self,
        repository: DomainRepository,
        *,
        creator_id: str,
        conversation_id: str,
    ) -> None:
        self.repo = repository
        self.creator_id = creator_id
        self.conversation_id = conversation_id
        self._pending: dict[int, PendingVoiceTurn] = {}

    async def validate(self) -> None:
        conversation = await self.repo.get(Conversation, self.conversation_id)
        owner_id = (
            await self.repo.owner_id(Conversation, self.conversation_id)
            if conversation is not None
            else None
        )
        if (
            conversation is None
            or owner_id != self.creator_id
            or conversation.status != ConversationStatus.ACTIVE.value
        ):
            raise LookupError("Conversation not found")

    async def build_request(self, command: str, turn_id: int) -> InferenceRequest:
        if turn_id in self._pending:
            raise RuntimeError(f"voice turn already committed: {turn_id}")

        correlation_id = str(uuid.uuid4())
        creator_message = await self.repo.add(
            Message(
                conversation_id=self.conversation_id,
                actor_id=self.creator_id,
                role="creator",
                content=command,
                route="deus",
                metadata_json={
                    "voice": True,
                    "voice_turn_id": turn_id,
                },
                correlation_id=correlation_id,
            )
        )
        self._pending[turn_id] = PendingVoiceTurn(
            creator_message_id=creator_message.id,
            correlation_id=correlation_id,
        )
        await self.repo.commit()

        history = await self.repo.list_messages(self.conversation_id, limit=20)
        return InferenceRequest(
            messages=conversation_messages(history),
            metadata={
                "conversation_id": self.conversation_id,
                "creator_id": self.creator_id,
                "route": "deus_voice",
                "voice_turn_id": turn_id,
                "cache_policy": "bypass",
                "latency_class": "interactive",
                "skip_health_probe": True,
            },
        )

    async def complete_turn(
        self,
        turn_id: int,
        response_text: str,
        provider: str,
    ) -> None:
        pending = self._pending.pop(turn_id, None)
        if pending is None:
            return
        await self.repo.add(
            Message(
                conversation_id=self.conversation_id,
                actor_id="deus",
                role="deus",
                content=response_text,
                route="deus",
                metadata_json={
                    "provider": provider,
                    "voice": True,
                    "voice_turn_id": turn_id,
                },
                correlation_id=pending.correlation_id,
            )
        )
        await self.repo.add_event(
            "deus_voice_response_generated",
            "conversation",
            self.conversation_id,
            self.creator_id,
            "creator",
            pending.correlation_id,
            {
                "creator_message_id": pending.creator_message_id,
                "provider": provider,
                "voice_turn_id": turn_id,
            },
        )
        await self.repo.commit()
