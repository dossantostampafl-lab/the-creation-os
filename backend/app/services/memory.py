from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.domain import Actor, DomainError, require_creator
from app.core.memory import MemoryType, build_memory_document, normalize_memory_text
from app.models.memory import CreatorMemory
from app.repositories.memory import MemoryRepository


class MemoryError(DomainError):
    pass


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
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
    ) -> tuple[CreatorMemory, bool]:
        require_creator(actor, "record creator memory")
        if not content.strip():
            raise MemoryError("Memory content cannot be empty")
        if not source.strip():
            raise MemoryError("Memory source cannot be empty")
        if importance < 1 or importance > 10:
            raise MemoryError("Memory importance must be between 1 and 10")

        document = build_memory_document(
            creator_id=actor.id,
            memory_type=memory_type,
            content=content,
            source=source,
            importance=importance,
            metadata=metadata,
        )
        existing = await self.repository.by_fingerprint(document.fingerprint)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        try:
            item = await self.repository.add(
                CreatorMemory(
                    creator_id=actor.id,
                    memory_type=document.memory_type.value,
                    source=source.strip(),
                    content=content,
                    normalized_content=document.normalized_content,
                    importance=importance,
                    metadata_json=metadata,
                    memory_fingerprint=document.fingerprint,
                )
            )
            await self.repository.add_event(
                item.id,
                actor.id,
                actor.role,
                correlation_id,
                {
                    "memory_id": item.id,
                    "creator_id": actor.id,
                    "memory_type": item.memory_type,
                    "source": item.source,
                    "importance": item.importance,
                    "memory_fingerprint": item.memory_fingerprint,
                },
            )
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.by_fingerprint(document.fingerprint)
            if existing is not None:
                return existing, False
            raise MemoryError("Memory could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def search(
        self,
        actor: Actor,
        *,
        query: str | None,
        memory_type: MemoryType | str | None,
        limit: int,
    ) -> list[CreatorMemory]:
        require_creator(actor, "search creator memory")
        resolved_type = MemoryType(memory_type).value if memory_type is not None else None
        normalized_query = normalize_memory_text(query) if query else None
        return await self.repository.search(
            creator_id=actor.id,
            query=normalized_query,
            memory_type=resolved_type,
            limit=limit,
        )
