from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ConsciousMemory


class ConsciousMemoryRepository:
    """Lote: busca ANN real via pgvector (2026-08-01). conscious_memory.embedding
    is now a native pgvector vector(8) column (migration 0026), with an HNSW
    index (ix_conscious_memory_embedding_hnsw) using cosine distance
    (vector_cosine_ops). search_by_embedding() ranks via the cosine_distance()
    operator directly in the query (pgvector-python's SQLAlchemy integration)
    so Postgres does the ranking using the index, not a bounded in-Python
    scan over up to 500 rows like the previous implementation. See
    ARCHITECTURE.md for the before/after and the measured performance
    difference at scale."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, memory_id: str) -> ConsciousMemory | None:
        return await self.session.get(ConsciousMemory, memory_id)

    async def add(self, item: ConsciousMemory) -> ConsciousMemory:
        self.session.add(item)
        await self.session.flush()
        return item

    async def all_candidates(self, limit: int = 500) -> list[ConsciousMemory]:
        stmt = select(ConsciousMemory).order_by(ConsciousMemory.created_at.desc()).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def search_by_embedding(self, embedding: list[float], *, limit: int) -> list[ConsciousMemory]:
        stmt = select(ConsciousMemory).order_by(ConsciousMemory.embedding.cosine_distance(embedding)).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def delete(self, memory_id: str) -> bool:
        item = await self.get(memory_id)
        if item is None:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
