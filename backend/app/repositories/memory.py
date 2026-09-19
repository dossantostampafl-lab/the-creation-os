from __future__ import annotations

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import CreatorMemory
from app.repositories.domain import DomainRepository


class MemoryRepository:
    """DEPRECATED for DEUS's memory recall (Lote: Convergência de memória de
    conversa, 2026-08-01) — see app/models/memory.py::CreatorMemory.
    Still backs app/services/memory.py (MemoryService) and the POST/GET
    /memory HTTP routes (app/api/memory.py), which remain active."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def by_fingerprint(self, fingerprint: str) -> CreatorMemory | None:
        return await self.session.scalar(
            select(CreatorMemory).where(CreatorMemory.memory_fingerprint == fingerprint)
        )

    async def add(self, item: CreatorMemory) -> CreatorMemory:
        self.session.add(item)
        await self.session.flush()
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
    ) -> list[CreatorMemory]:
        conditions = [CreatorMemory.creator_id == creator_id, CreatorMemory.importance >= min_importance]
        if memory_type is not None:
            conditions.append(CreatorMemory.memory_type == memory_type)
        if memory_types is not None:
            conditions.append(CreatorMemory.memory_type.in_(memory_types))
        if query:
            pattern = f"%{query}%"
            conditions.append(
                or_(
                    CreatorMemory.normalized_content.ilike(pattern),
                    cast(CreatorMemory.metadata_json, String).ilike(pattern),
                    CreatorMemory.source.ilike(pattern),
                )
            )
        statement = (
            select(CreatorMemory)
            .where(*conditions)
            .order_by(CreatorMemory.importance.desc(), CreatorMemory.created_at.desc(), CreatorMemory.id)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def add_event(
        self,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict,
    ) -> None:
        await self.domain.add_event(
            "creator_memory_recorded",
            "creator_memory",
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
