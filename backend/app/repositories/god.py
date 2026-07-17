from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Conversation, Message
from app.models.god import GodConversationInteraction
from app.repositories.domain import DomainRepository
from app.repositories.memory import MemoryRepository


class GodConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)
        self.memory = MemoryRepository(session)

    async def conversation(self, conversation_id: str, *, lock: bool = False) -> Conversation | None:
        statement = select(Conversation).where(Conversation.id == conversation_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def interaction(self, conversation_id: str, idempotency_key: str) -> GodConversationInteraction | None:
        return await self.session.scalar(
            select(GodConversationInteraction).where(
                GodConversationInteraction.conversation_id == conversation_id,
                GodConversationInteraction.idempotency_key == idempotency_key,
            )
        )

    async def add_message(self, item: Message) -> Message:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_interaction(self, item: GodConversationInteraction) -> GodConversationInteraction:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict,
    ) -> None:
        await self.domain.add_event(
            event_type,
            aggregate_type,
            aggregate_id,
            actor_id,
            actor_role,
            correlation_id,
            payload,
        )

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
