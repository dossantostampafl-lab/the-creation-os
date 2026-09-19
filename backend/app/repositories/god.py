from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import ConversationStatus
from app.models.entities import Agent, ConsciousMemory, Conversation, ConversationMemory, Inception, Message, Mission, Universe
from app.models.god import GodConversationInteraction
from app.models.memory import CreatorMemory
from app.repositories.domain import DomainRepository
from app.repositories.memory import MemoryRepository

# Lote: DEUS inicia conversa automaticamente após login. Distinct from
# CreatorRecallRepository.MEMORY_ANCHOR_CONVERSATION_TITLE ("__creator_memory__")
# — that anchor holds conversation_memory rows (Creator-wide recall), this one
# holds the actual DEUS chat thread the Creator Interface displays. Same
# get-or-create-by-title pattern, different Conversation.
DEUS_CONVERSATION_ANCHOR_TITLE = "__deus_conversation__"


@dataclass(frozen=True)
class ConversationMemoryCandidate:
    """Adapts a ConversationMemory row's value_json into the exact attribute
    shape app.core.memory.select_memory_context() already expects (id,
    memory_type, source, content, importance, normalized_content,
    memory_fingerprint) — the same shape CreatorMemory rows have — so that
    function is reused unchanged for the new source. See ARCHITECTURE.md,
    "Lote: Convergência de memória de conversa"."""

    id: str
    memory_type: str
    source: str
    content: str
    importance: int
    normalized_content: str
    memory_fingerprint: str


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

    async def anchor_conversation_id(self, creator_id: str) -> str:
        existing = await self.session.scalar(
            select(Conversation.id).where(
                Conversation.creator_id == creator_id,
                Conversation.title == DEUS_CONVERSATION_ANCHOR_TITLE,
            )
        )
        if existing is not None:
            return existing
        conversation = Conversation(
            creator_id=creator_id, title=DEUS_CONVERSATION_ANCHOR_TITLE, status=ConversationStatus.ACTIVE.value
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation.id

    async def latest_greeting_message(self, conversation_id: str) -> Message | None:
        return await self.session.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.metadata_json["greeting"].as_boolean().is_(True),
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )

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

    # SYSTEM_QUERY read-only counts. Minimal, purpose-built queries — not a
    # general-purpose reporting layer — added here (not to TreeCoreRepository
    # or a Mission/Inception repository) to keep this lote's footprint to
    # exactly what SYSTEM_QUERY needs, per AUDITORIA: SYSTEM_QUERY section 4.

    async def mission_counts(self, creator_id: str) -> dict[str, int]:
        total = await self.session.scalar(select(func.count()).select_from(Mission).where(Mission.creator_id == creator_id))
        running = await self.session.scalar(
            select(func.count())
            .select_from(Mission)
            .where(
                Mission.creator_id == creator_id,
                func.lower(Mission.status).in_(["planned", "authorized", "distributed", "executing"]),
            )
        )
        return {"total": int(total or 0), "running": int(running or 0)}

    async def pending_inception_count(self, creator_id: str) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(Inception)
            .join(Conversation, Conversation.id == Inception.conversation_id)
            .where(
                Conversation.creator_id == creator_id,
                func.lower(Inception.status).in_(["proposed", "submitted", "pending"]),
            )
        )
        return int(value or 0)

    async def universe_counts(self) -> dict[str, int]:
        total = await self.session.scalar(select(func.count()).select_from(Universe))
        active = await self.session.scalar(select(func.count()).select_from(Universe).where(Universe.active.is_(True)))
        return {"total": int(total or 0), "active": int(active or 0)}

    async def agent_counts(self) -> dict[str, int]:
        total = await self.session.scalar(select(func.count()).select_from(Agent))
        available = await self.session.scalar(
            select(func.count()).select_from(Agent).where(Agent.enabled.is_(True), Agent.status == "idle")
        )
        return {"total": int(total or 0), "available": int(available or 0)}

    # Lote: Convergência de memória de conversa. GOD's memory recall is
    # Creator-wide (a Creator's memories are recalled regardless of which
    # Conversation they originated in) — the same observable scope
    # CreatorMemory had. ConversationMemory rows are scoped to one
    # conversation_id each, so this joins through Conversation to search
    # across every Conversation belonging to the Creator, not just the
    # active one. Mirrors MemoryRepository.search()'s DB-side filter/order
    # (importance DESC, then recency) before the same Python-side
    # select_memory_context() re-ranks by query relevance.
    async def conversation_memory_candidates(
        self,
        creator_id: str,
        *,
        memory_types: list[str] | None = None,
        min_importance: int = 1,
        limit: int = 50,
    ) -> list[ConversationMemoryCandidate]:
        importance = ConversationMemory.value_json["importance"].as_integer()
        memory_type = ConversationMemory.value_json["memory_type"].as_string()
        stmt = (
            select(ConversationMemory)
            .join(Conversation, Conversation.id == ConversationMemory.conversation_id)
            .where(Conversation.creator_id == creator_id, importance >= min_importance)
        )
        if memory_types is not None:
            stmt = stmt.where(memory_type.in_(memory_types))
        stmt = stmt.order_by(importance.desc(), ConversationMemory.created_at.desc()).limit(limit)
        rows = (await self.session.scalars(stmt)).all()
        return [
            ConversationMemoryCandidate(
                id=row.id,
                memory_type=row.value_json.get("memory_type", ""),
                source=row.value_json.get("source", ""),
                content=row.value_json.get("content", ""),
                importance=int(row.value_json.get("importance", 1)),
                normalized_content=row.value_json.get("normalized_content", ""),
                memory_fingerprint=row.value_json.get("memory_fingerprint", row.key),
            )
            for row in rows
        ]

    async def memory_item_counts(self, creator_id: str) -> dict[str, int]:
        creator_memory = await self.session.scalar(
            select(func.count()).select_from(CreatorMemory).where(CreatorMemory.creator_id == creator_id)
        )
        conscious_memory = await self.session.scalar(select(func.count()).select_from(ConsciousMemory))
        return {"creator_memory_items": int(creator_memory or 0), "conscious_memory_items": int(conscious_memory or 0)}
