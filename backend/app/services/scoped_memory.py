from __future__ import annotations

from app.core.domain import DomainError
from app.repositories.domain import DomainRepository
from app.repositories.scoped_memory import ScopedMemoryRepository


class ScopedMemoryError(DomainError):
    pass


class ScopedMemoryService:
    """MemoryStore-conformant service for ConversationMemory/MissionMemory/
    UniverseMemory — one instance per (model, parent scope). Delete is
    available here (these are the "operational" layers the Lote 2.5 prompt
    allows deletion on); Chronicles remain append-only and untouched by this
    service or any other in this lote."""

    def __init__(self, repository: ScopedMemoryRepository, *, aggregate_type: str, actor_id: str, actor_role: str) -> None:
        self.repository = repository
        self.aggregate_type = aggregate_type
        self.actor_id = actor_id
        self.actor_role = actor_role

    async def get(self, key: str):
        return await self.repository.get_by_key(key)

    async def set(self, key: str, value: dict, *, correlation_id: str):
        if not key.strip():
            raise ScopedMemoryError("Memory key cannot be empty")
        item = await self.repository.upsert(key, value)
        await self._event(f"{self.aggregate_type}_set", item.id, correlation_id, {"key": key})
        await self.repository.commit()
        return item

    async def search(self, query: str | None = None, *, limit: int = 20):
        return await self.repository.search(query, limit)

    async def delete(self, key: str, *, correlation_id: str) -> bool:
        existing = await self.repository.get_by_key(key)
        if existing is None:
            return False
        deleted = await self.repository.delete(key)
        if deleted:
            await self._event(f"{self.aggregate_type}_deleted", existing.id, correlation_id, {"key": key})
            await self.repository.commit()
        return deleted

    async def _event(self, event_type: str, aggregate_id: str, correlation_id: str, payload: dict) -> None:
        await DomainRepository(self.repository.session).add_event(
            event_type, self.aggregate_type, aggregate_id, self.actor_id, self.actor_role, correlation_id, payload
        )
