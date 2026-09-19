from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.contracts import CacheContext
from app.models.cache import CacheEvent, SemanticCacheEntry


class CacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _same_nullable(column: Any, value: str | None) -> Any:
        return column.is_(None) if value is None else column == value

    async def exact(self, exact_key: str, now: datetime) -> SemanticCacheEntry | None:
        return await self.session.scalar(
            select(SemanticCacheEntry)
            .where(
                SemanticCacheEntry.exact_key == exact_key,
                SemanticCacheEntry.validation_status == "VALIDATED",
                SemanticCacheEntry.expires_at > now,
            )
            .limit(1)
        )

    async def semantic_candidates(
        self,
        *,
        context: CacheContext,
        embedding: list[float],
        embedding_model: str,
        embedding_version: str,
        limit: int,
        now: datetime,
    ) -> list[tuple[SemanticCacheEntry, float]]:
        dimension = len(embedding)
        embedding_column: Any = SemanticCacheEntry.embedding
        if dimension == 1536:
            embedding_column = cast(SemanticCacheEntry.embedding, Vector(1536))
        distance = embedding_column.cosine_distance(embedding).label("distance")
        conditions = [
            SemanticCacheEntry.creator_scope == context.creator_scope,
            self._same_nullable(SemanticCacheEntry.universe_scope, context.universe_scope),
            SemanticCacheEntry.intent_class == context.intent.value,
            SemanticCacheEntry.embedding_model == embedding_model,
            SemanticCacheEntry.embedding_version == embedding_version,
            SemanticCacheEntry.embedding_dimensions == dimension,
            SemanticCacheEntry.context_hash == context.context_hash,
            self._same_nullable(SemanticCacheEntry.context_version, context.context_version),
            self._same_nullable(SemanticCacheEntry.knowledge_version, context.knowledge_version),
            self._same_nullable(SemanticCacheEntry.retrieval_fingerprint, context.retrieval_fingerprint),
            SemanticCacheEntry.generation_profile_hash == context.generation_profile_hash,
            SemanticCacheEntry.policy_version == context.policy_version,
            SemanticCacheEntry.authorization_fingerprint == context.authorization_fingerprint,
            SemanticCacheEntry.tool_state_class == context.tool_state_class,
            SemanticCacheEntry.validation_status == "VALIDATED",
            SemanticCacheEntry.expires_at > now,
        ]
        rows = (
            await self.session.execute(
                select(SemanticCacheEntry, distance)
                .where(and_(*conditions))
                .order_by(distance.asc())
                .limit(limit)
            )
        ).all()
        return [(entry, float(value)) for entry, value in rows if value is not None]

    async def upsert(self, *, values: dict[str, Any]) -> SemanticCacheEntry:
        statement = insert(SemanticCacheEntry).values(**values)
        excluded = statement.excluded
        statement = (
            statement.on_conflict_do_update(
                index_elements=[SemanticCacheEntry.exact_key],
                set_={
                    "creator_scope": excluded.creator_scope,
                    "universe_scope": excluded.universe_scope,
                    "intent_class": excluded.intent_class,
                    "sensitivity": excluded.sensitivity,
                    "normalized_query": excluded.normalized_query,
                    "embedding": excluded.embedding,
                    "embedding_model": excluded.embedding_model,
                    "embedding_version": excluded.embedding_version,
                    "embedding_dimensions": excluded.embedding_dimensions,
                    "context_hash": excluded.context_hash,
                    "context_version": excluded.context_version,
                    "knowledge_version": excluded.knowledge_version,
                    "retrieval_fingerprint": excluded.retrieval_fingerprint,
                    "generation_profile_hash": excluded.generation_profile_hash,
                    "policy_version": excluded.policy_version,
                    "authorization_fingerprint": excluded.authorization_fingerprint,
                    "tool_state_class": excluded.tool_state_class,
                    "response_json": excluded.response_json,
                    "validation_status": "VALIDATED",
                    "confidence": excluded.confidence,
                    "tags": excluded.tags,
                    "expires_at": excluded.expires_at,
                },
            )
            .returning(SemanticCacheEntry)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def record_hit(self, entry_id: str) -> None:
        await self.session.execute(
            update(SemanticCacheEntry)
            .where(SemanticCacheEntry.id == entry_id)
            .values(hit_count=SemanticCacheEntry.hit_count + 1, last_hit_at=datetime.now(timezone.utc))
        )

    async def invalidate_tags(self, tags: list[str], creator_scope: str | None = None) -> list[str]:
        if not tags:
            return []
        conditions: list[Any] = [SemanticCacheEntry.validation_status == "VALIDATED"]
        if creator_scope is not None:
            conditions.append(SemanticCacheEntry.creator_scope == creator_scope)
        tag_filters = [SemanticCacheEntry.tags.any(tag) for tag in tags]
        statement = (
            update(SemanticCacheEntry)
            .where(and_(*conditions), or_(*tag_filters))
            .values(validation_status="INVALID")
            .returning(SemanticCacheEntry.exact_key)
        )
        return list((await self.session.scalars(statement)).all())

    async def add_event(
        self,
        *,
        event_type: str,
        reason_code: str,
        creator_scope: str | None = None,
        cache_entry_id: str | None = None,
        decision: str | None = None,
        semantic_score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CacheEvent:
        event = CacheEvent(
            cache_entry_id=cache_entry_id,
            event_type=event_type,
            creator_scope=creator_scope,
            decision=decision,
            semantic_score=semantic_score,
            reason_code=reason_code,
            metadata_json=metadata or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def counts(self) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        total = int(await self.session.scalar(select(func.count()).select_from(SemanticCacheEntry)) or 0)
        valid = int(
            await self.session.scalar(
                select(func.count())
                .select_from(SemanticCacheEntry)
                .where(SemanticCacheEntry.validation_status == "VALIDATED", SemanticCacheEntry.expires_at > now)
            )
            or 0
        )
        invalid = int(
            await self.session.scalar(
                select(func.count())
                .select_from(SemanticCacheEntry)
                .where(SemanticCacheEntry.validation_status == "INVALID")
            )
            or 0
        )
        return {"total": total, "valid": valid, "invalid": invalid}
