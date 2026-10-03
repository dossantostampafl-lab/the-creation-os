from __future__ import annotations

import asyncio
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
        context_builder=None,
        turn_store=None,
        session_id: str | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.turn_store = turn_store
        self.session_id = session_id or str(uuid.uuid4())
        self._claims: dict = {}
        self._renewals: dict = {}
        self._trace_ids: dict = {}
        self._dependencies: dict = {}
        self.renewal_interval_seconds = 20.0
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

        if self.turn_store is not None:
            request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'creation:voice:' + self.conversation_id + ':' + self.session_id + ':' + str(turn_id)))
            claimed = await self.turn_store.claim(self.creator_id, self.conversation_id, request_id, command)
            if claimed.response is not None:
                raise RuntimeError('voice turn already completed')
            self._claims[turn_id] = claimed
            generation = asyncio.current_task()
            async def renew():
                while True:
                    await asyncio.sleep(self.renewal_interval_seconds)
                    try:
                        renewed = await self.turn_store.renew(claimed)
                    except Exception:
                        renewed = False
                    if not renewed:
                        if generation:
                            generation.cancel()
                        return
            self._renewals[turn_id] = asyncio.create_task(renew())
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
        packet = await self.context_builder.build(self.creator_id, self.conversation_id, command, 'voice', history) if self.context_builder is not None else None
        if packet:
            self._trace_ids[turn_id] = packet.trace_id
            self._dependencies[turn_id] = packet.trace['dependency_revision_ids']
        from app.config import settings
        if settings.deus_knowledge_ingestion_enabled:
            from app.knowledge.contracts import Candidate, Scope
            from app.knowledge.service import KnowledgeService
            await KnowledgeService(self.repo.session).write(Scope(creator_id=self.creator_id), Candidate(title='Conversa por voz', content=command, source_type='message', source_id=creator_message.id), 'message:' + creator_message.id)
            await self.repo.commit()
        return InferenceRequest(
            messages=packet.messages if packet else conversation_messages(history),
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
        deus_message = await self.repo.add(
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
                    **({'context_trace_id': self._trace_ids.pop(turn_id)} if turn_id in self._trace_ids else {}),
                },
                correlation_id=pending.correlation_id,
            )
        )
        from app.config import settings
        if settings.deus_knowledge_ingestion_enabled and len(self._dependencies.get(turn_id, [])) <= 32:
            from app.knowledge.contracts import Candidate, Scope
            from app.knowledge.service import KnowledgeService
            await KnowledgeService(self.repo.session).write(
                Scope(creator_id=self.creator_id),
                Candidate(title='Resposta de Deus por voz', content=response_text,
                          kind='derived_note', source_type='message', source_id=deus_message.id,
                          dependencies=self._dependencies.get(turn_id, [])),
                'message:' + deus_message.id,
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
        claimed = self._claims.get(turn_id)
        if claimed is not None:
            await self.turn_store.finish_in_session(self.repo.session, claimed,
                {'response': response_text, 'provider': provider}, 'completed')
        await self.repo.commit()
        self._claims.pop(turn_id, None)
        self._dependencies.pop(turn_id, None)

        claimed = None
        renewal = self._renewals.pop(turn_id, None)
        if renewal:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)
        if claimed is not None:
            await self.turn_store.finish(claimed, {'response': response_text, 'provider': provider}, 'completed')

    async def abort_turn(self, turn_id: int) -> None:
        from app.services.deus_turns import TurnConflict
        claimed = self._claims.pop(turn_id, None)
        renewal = self._renewals.pop(turn_id, None)
        if renewal:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)
        if claimed is not None:
            try:
                await self.turn_store.finish(claimed, None, 'interrupted')
            except TurnConflict:
                pass
        self._pending.pop(turn_id, None)
        self._trace_ids.pop(turn_id, None)
        self._dependencies.pop(turn_id, None)

    async def close(self) -> None:
        for turn_id in list(self._claims):
            await self.abort_turn(turn_id)
