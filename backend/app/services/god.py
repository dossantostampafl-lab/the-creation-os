from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.domain import Actor, ConversationStatus, DomainError, require_creator
from app.core.god import build_god_interaction, canonical_request_fingerprint
from app.core.memory import MemoryType, normalize_memory_text, select_memory_context
from app.models.entities import Message
from app.models.god import GodConversationInteraction
from app.repositories.god import GodConversationRepository
from app.services.domain import NotFoundError


class GodConversationError(DomainError):
    pass


class GodIdempotencyConflict(GodConversationError):
    pass


class GodConversationService:
    def __init__(self, repository: GodConversationRepository) -> None:
        self.repository = repository

    async def interact(
        self,
        actor: Actor,
        conversation_id: str,
        message: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> tuple[GodConversationInteraction, bool]:
        require_creator(actor, "speak with GOD")
        conversation = await self.repository.conversation(conversation_id, lock=True)
        if conversation is None or conversation.creator_id != actor.id:
            await self.repository.rollback()
            raise NotFoundError("Conversation not found")
        if conversation.status != ConversationStatus.ACTIVE.value:
            await self.repository.rollback()
            raise GodConversationError("GOD conversation orchestration requires an active Conversation")

        existing = await self.repository.interaction(conversation_id, idempotency_key)
        if existing is not None:
            self._ensure_same_request(existing, conversation_id, message, idempotency_key)
            await self.repository.commit()
            return existing, False

        try:
            memory_context = await self._memory_context(actor, message)
            document = build_god_interaction(conversation_id, message, idempotency_key, memory_context)
            creator_message = await self.repository.add_message(Message(
                conversation_id=conversation_id,
                actor_id=actor.id,
                role=actor.role,
                content=message,
                route="god",
                correlation_id=correlation_id,
                metadata_json={"idempotency_key": idempotency_key, "god_interaction": True},
            ))
            god_message = await self.repository.add_message(Message(
                conversation_id=conversation_id,
                actor_id="god",
                role="god",
                content=document.reply["message"],
                route="god",
                correlation_id=correlation_id,
                metadata_json={
                    "interaction_type": document.interaction_type.value,
                    "fingerprint": document.fingerprint,
                    "memory_context": memory_context,
                    "next_action": document.next_action,
                },
            ))
            response_payload = {
                "conversation_id": conversation_id,
                "message_id": creator_message.id,
                "god_message_id": god_message.id,
                "interaction_type": document.interaction_type.value,
                "reply": document.reply,
                "potential_detected": document.potential_detected,
                "next_action": document.next_action,
                "memory_context": memory_context,
                "memory_ids": [item["id"] for item in memory_context],
                "fingerprint": document.fingerprint,
            }
            item = await self.repository.add_interaction(GodConversationInteraction(
                conversation_id=conversation_id,
                creator_message_id=creator_message.id,
                god_message_id=god_message.id,
                idempotency_key=idempotency_key,
                interaction_type=document.interaction_type.value,
                request_payload={
                    "message": message,
                    "idempotency_key": idempotency_key,
                    "policy_version": document.reply["policy_version"],
                    "request_fingerprint": document.request_fingerprint,
                    "memory_context": memory_context,
                    "memory_ids": [item["id"] for item in memory_context],
                },
                response_payload=response_payload,
                potential_detected=document.potential_detected,
                fingerprint=document.fingerprint,
            ))
            await self.repository.add_event(
                "god_conversation_interaction_completed",
                "conversation",
                conversation_id,
                actor.id,
                actor.role,
                correlation_id,
                {
                    "interaction_id": item.id,
                    "creator_message_id": creator_message.id,
                    "god_message_id": god_message.id,
                    "interaction_type": item.interaction_type,
                    "idempotency_key": idempotency_key,
                    "fingerprint": item.fingerprint,
                    "memory_ids": [memory["id"] for memory in memory_context],
                    "memory_fingerprints": [memory["fingerprint"] for memory in memory_context],
                    "potential_detected": item.potential_detected,
                    "next_action": document.next_action,
                },
            )
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.interaction(conversation_id, idempotency_key)
            if existing is not None:
                self._ensure_same_request(existing, conversation_id, message, idempotency_key)
                return existing, False
            raise GodConversationError("GOD interaction could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    def _ensure_same_request(
        self,
        existing: GodConversationInteraction,
        conversation_id: str,
        message: str,
        idempotency_key: str,
    ) -> None:
        incoming = canonical_request_fingerprint(conversation_id, message, idempotency_key)
        persisted = existing.request_payload.get("request_fingerprint")
        if persisted is None:
            persisted = canonical_request_fingerprint(
                existing.conversation_id,
                str(existing.request_payload.get("message", "")),
                str(existing.request_payload.get("idempotency_key", existing.idempotency_key)),
            )
        if persisted != incoming:
            raise GodIdempotencyConflict("Idempotency key already used with a different GOD request payload")

    async def _memory_context(self, actor: Actor, message: str) -> list[dict]:
        candidates = await self.repository.memory.search(
            creator_id=actor.id,
            query=normalize_memory_text(message),
            memory_types=[item.value for item in MemoryType],
            min_importance=1,
            limit=50,
        )
        return [
            {
                "id": item.id,
                "memory_type": item.memory_type,
                "source": item.source,
                "content": item.content,
                "importance": item.importance,
                "fingerprint": item.fingerprint,
                "relevance_score": item.relevance_score,
            }
            for item in select_memory_context(candidates, query=message, limit=5)
        ]
