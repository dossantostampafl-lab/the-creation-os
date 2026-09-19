from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ConversationMemory, MissionMemory, UniverseMemory

ScopedMemoryModel = TypeVar("ScopedMemoryModel", ConversationMemory, MissionMemory, UniverseMemory)


class ScopedMemoryRepository(Generic[ScopedMemoryModel]):
    """Generic repository for the three key/value memory layers that share an
    identical shape (id, <parent>_id, key, value_json, created_at, updated_at):
    ConversationMemory, MissionMemory, UniverseMemory (backend/app/models/entities.py).
    Parameterized by model class, the name of its parent-scope foreign key
    attribute, and the parent id itself, instead of writing the same CRUD
    three times. None of the three tables has a unique constraint on
    (parent_id, key) in 0001_initial, so `upsert` does the find-then-update-or-
    insert at the application level."""

    def __init__(self, session: AsyncSession, model: type[ScopedMemoryModel], parent_attr: str, parent_id: str) -> None:
        self.session = session
        self.model = model
        self.parent_attr = parent_attr
        self.parent_id = parent_id

    def _scope(self):
        return getattr(self.model, self.parent_attr) == self.parent_id

    async def get_by_key(self, key: str) -> ScopedMemoryModel | None:
        stmt = select(self.model).where(self._scope(), self.model.key == key)
        return await self.session.scalar(stmt)

    async def upsert(self, key: str, value: dict) -> ScopedMemoryModel:
        existing = await self.get_by_key(key)
        if existing is not None:
            existing.value_json = value
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing
        item = self.model(**{self.parent_attr: self.parent_id, "key": key, "value_json": value})
        self.session.add(item)
        await self.session.flush()
        return item

    async def search(self, query: str | None, limit: int) -> list[ScopedMemoryModel]:
        stmt = select(self.model).where(self._scope())
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(or_(self.model.key.ilike(pattern), cast(self.model.value_json, String).ilike(pattern)))
        stmt = stmt.order_by(self.model.updated_at.desc()).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def delete(self, key: str) -> bool:
        existing = await self.get_by_key(key)
        if existing is None:
            return False
        await self.session.delete(existing)
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
