from __future__ import annotations

from app.ai.fake import FakeEmbeddingModel
from app.ai.interfaces import EmbeddingModel
from app.config import settings
from app.core.domain import Actor, DomainError, require_creator
from app.models.entities import ConsciousMemory
from app.repositories.conscious_memory import ConsciousMemoryRepository
from app.repositories.domain import DomainRepository


class ConsciousMemoryError(DomainError):
    pass


class ConsciousMemoryService:
    """MemoryStore-conformant service for the fourth memory layer.

    Consolidation (writing a new row) is deliberately NOT a generic public
    "set" — Lote 2.5 requires it to happen only through one of two triggers:

    - consolidate_from_mission: called by ManifestationService.manifest()
      after a *new* (non-idempotent) successful manifestation. Shares that
      caller's session/transaction and does not commit itself, so a rollback
      of the manifestation also rolls back the consolidated memory.
    - consolidate_explicit: a real Creator decision to persist knowledge,
      gated by require_creator like every other explicit-decision action in
      this codebase. Commits its own transaction (standalone call).

    No other method writes a ConsciousMemory row.
    """

    def __init__(self, repository: ConsciousMemoryRepository, embedding_model: EmbeddingModel | None = None) -> None:
        self.repository = repository
        self.embedding_model = embedding_model or FakeEmbeddingModel()

    async def get(self, memory_id: str) -> ConsciousMemory | None:
        return await self.repository.get(memory_id)

    async def search(self, query: str | None = None, *, limit: int = 10) -> list[ConsciousMemory]:
        if not query or not query.strip():
            return await self.repository.all_candidates(limit)
        embedding = await self.embedding_model.embed(query)
        return await self.repository.search_by_embedding(embedding, limit=limit)

    async def delete(self, memory_id: str, *, actor: Actor, correlation_id: str) -> bool:
        require_creator(actor, "delete conscious memory")
        existing = await self.repository.get(memory_id)
        if existing is None:
            return False
        deleted = await self.repository.delete(memory_id)
        if deleted:
            await DomainRepository(self.repository.session).add_event(
                "conscious_memory_deleted", "conscious_memory", memory_id, actor.id, actor.role, correlation_id, {}
            )
            await self.repository.commit()
        return deleted

    async def consolidate_from_mission(self, mission, *, correlation_id: str) -> ConsciousMemory:
        content = f"Mission '{mission.title}' manifested. Objective: {mission.objective}"
        return await self._consolidate(
            source_type="mission",
            source_id=mission.id,
            content=content,
            metadata={"trigger": "mission_manifested"},
            actor_id="system",
            actor_role="worker",
            correlation_id=correlation_id,
        )

    async def consolidate_explicit(
        self,
        actor: Actor,
        *,
        source_type: str,
        source_id: str,
        content: str,
        metadata: dict | None = None,
        correlation_id: str,
    ) -> ConsciousMemory:
        require_creator(actor, "consolidate conscious memory")
        if not content.strip():
            raise ConsciousMemoryError("Conscious memory content cannot be empty")
        item = await self._consolidate(
            source_type=source_type,
            source_id=source_id,
            content=content,
            metadata={**(metadata or {}), "trigger": "explicit_creator_decision"},
            actor_id=actor.id,
            actor_role=actor.role,
            correlation_id=correlation_id,
        )
        await self.repository.commit()
        return item

    async def _consolidate(
        self, *, source_type: str, source_id: str, content: str, metadata: dict, actor_id: str, actor_role: str, correlation_id: str
    ) -> ConsciousMemory:
        embedding = await self.embedding_model.embed(content)
        expected_dim = settings.conscious_memory_embedding_dim
        if len(embedding) != expected_dim:
            raise ConsciousMemoryError(
                f"Embedding dimension mismatch: model returned {len(embedding)}, expected {expected_dim}"
            )
        item = await self.repository.add(
            ConsciousMemory(
                source_type=source_type,
                source_id=source_id,
                content=content,
                metadata_json=metadata,
                embedding=embedding,
            )
        )
        await DomainRepository(self.repository.session).add_event(
            "conscious_memory_consolidated",
            "conscious_memory",
            item.id,
            actor_id,
            actor_role,
            correlation_id,
            {"source_type": source_type, "source_id": source_id, "trigger": metadata.get("trigger")},
        )
        return item
