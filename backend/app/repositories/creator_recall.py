from __future__ import annotations

from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import ConversationStatus
from app.models.entities import Conversation, ConversationMemory
from app.repositories.domain import DomainRepository

MEMORY_ANCHOR_CONVERSATION_TITLE = "__creator_memory__"


class CreatorRecallRepository:
    """Lote: fechar gap de POST /memory (2026-08-01). conversation_memory
    rows are each scoped to one Conversation, but POST /memory is
    Creator-wide with no Conversation of its own — same pattern
    app/services/opportunities.py already uses for its own synthetic
    "Opportunity Discovery" Conversation. Resolves/creates one dedicated,
    stable anchor Conversation per Creator so
    GodConversationRepository.conversation_memory_candidates() (unchanged,
    still a Creator-wide join across every Conversation) picks these rows
    up automatically — no schema change to conversation_memory."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def anchor_conversation_id(self, creator_id: str) -> str:
        existing = await self.session.scalar(
            select(Conversation.id).where(
                Conversation.creator_id == creator_id,
                Conversation.title == MEMORY_ANCHOR_CONVERSATION_TITLE,
            )
        )
        if existing is not None:
            return existing
        conversation = await self.domain.add(
            Conversation(creator_id=creator_id, title=MEMORY_ANCHOR_CONVERSATION_TITLE, status=ConversationStatus.ACTIVE.value)
        )
        return conversation.id

    async def search(
        self,
        creator_id: str,
        *,
        query: str | None,
        memory_type: str | None,
        min_importance: int,
        limit: int,
    ) -> list[ConversationMemory]:
        anchor_id = await self.anchor_conversation_id(creator_id)
        importance = ConversationMemory.value_json["importance"].as_integer()
        stmt = select(ConversationMemory).where(ConversationMemory.conversation_id == anchor_id, importance >= min_importance)
        if memory_type is not None:
            stmt = stmt.where(ConversationMemory.value_json["memory_type"].as_string() == memory_type)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(cast(ConversationMemory.value_json, String).ilike(pattern))
        stmt = stmt.order_by(importance.desc(), ConversationMemory.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())
