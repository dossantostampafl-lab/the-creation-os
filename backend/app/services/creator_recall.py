from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.domain import Actor, DomainError, require_creator
from app.core.memory import MemoryType, build_memory_document, normalize_memory_text
from app.models.entities import ConversationMemory
from app.repositories.creator_recall import CreatorRecallRepository
from app.repositories.scoped_memory import ScopedMemoryRepository
from app.services.scoped_memory import ScopedMemoryService


class CreatorRecallError(DomainError):
    pass


@dataclass(frozen=True)
class RememberedMemory:
    """Duck-types the same attributes CreatorMemory rows had
    (app/models/memory.py), so app/api/memory.py::memory_response() needs
    no change: id, creator_id, memory_type, source, content, importance,
    metadata_json, memory_fingerprint, created_at."""

    id: str
    creator_id: str
    memory_type: str
    source: str
    content: str
    importance: int
    metadata_json: dict
    memory_fingerprint: str
    created_at: datetime


def _to_remembered(creator_id: str, row: ConversationMemory) -> RememberedMemory:
    value = row.value_json
    return RememberedMemory(
        id=row.id,
        creator_id=creator_id,
        memory_type=value.get("memory_type", ""),
        source=value.get("source", ""),
        content=value.get("content", ""),
        importance=int(value.get("importance", 1)),
        metadata_json=value.get("metadata", {}),
        memory_fingerprint=value.get("memory_fingerprint", row.key),
        created_at=row.created_at,
    )


class CreatorRecallService:
    """Backs POST/GET /memory (app/api/memory.py) since Lote: fechar gap de
    POST /memory (2026-08-01) — writes/reads conversation_memory via the
    Creator's anchor Conversation, replacing MemoryService/CreatorMemory
    for this route. Same public shape as the old MemoryService.remember()/
    search() so the route only needed to swap which service is injected.
    MemoryService/MemoryRepository/CreatorMemory remain deprecated,
    untouched, and are no longer called by any active code path."""

    def __init__(self, repository: CreatorRecallRepository) -> None:
        self.repository = repository

    async def remember(
        self,
        actor: Actor,
        *,
        memory_type: MemoryType | str,
        content: str,
        source: str,
        importance: int,
        metadata: dict,
        correlation_id: str,
    ) -> tuple[RememberedMemory, bool]:
        require_creator(actor, "record creator memory")
        if not content.strip():
            raise CreatorRecallError("Memory content cannot be empty")
        if not source.strip():
            raise CreatorRecallError("Memory source cannot be empty")
        if importance < 1 or importance > 10:
            raise CreatorRecallError("Memory importance must be between 1 and 10")

        document = build_memory_document(
            creator_id=actor.id,
            memory_type=memory_type,
            content=content,
            source=source,
            importance=importance,
            metadata=metadata,
        )
        anchor_id = await self.repository.anchor_conversation_id(actor.id)
        scoped_repository = ScopedMemoryRepository(self.repository.session, ConversationMemory, "conversation_id", anchor_id)
        existing = await scoped_repository.get_by_key(document.fingerprint)
        created = existing is None
        scoped_service = ScopedMemoryService(
            scoped_repository, aggregate_type="creator_memory", actor_id=actor.id, actor_role=actor.role
        )
        value_json = {
            "memory_type": document.memory_type.value,
            "source": source.strip(),
            "content": content,
            "normalized_content": document.normalized_content,
            "importance": importance,
            "metadata": metadata,
            "memory_fingerprint": document.fingerprint,
        }
        item = await scoped_service.set(document.fingerprint, value_json, correlation_id=correlation_id)
        return _to_remembered(actor.id, item), created

    async def search(
        self,
        actor: Actor,
        *,
        query: str | None,
        memory_type: MemoryType | str | None,
        min_importance: int = 1,
        limit: int,
    ) -> list[RememberedMemory]:
        require_creator(actor, "search creator memory")
        resolved_type = MemoryType(memory_type).value if memory_type is not None else None
        normalized_query = normalize_memory_text(query) if query else None
        rows = await self.repository.search(
            actor.id, query=normalized_query, memory_type=resolved_type, min_importance=min_importance, limit=limit
        )
        return [_to_remembered(actor.id, row) for row in rows]
