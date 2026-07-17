from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.perception import CreatorNotification, PerceptionRun, PerceptionSource
from app.repositories.domain import DomainRepository


class PerceptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def source_by_name(self, name: str) -> PerceptionSource | None:
        return await self.session.scalar(select(PerceptionSource).where(PerceptionSource.name == name))

    async def source(self, source_id: str, *, lock: bool = False) -> PerceptionSource | None:
        stmt = select(PerceptionSource).where(PerceptionSource.id == source_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def sources(self, *, universe: str | None = None) -> list[PerceptionSource]:
        stmt = select(PerceptionSource)
        if universe:
            stmt = stmt.where(PerceptionSource.universe == universe)
        result = await self.session.scalars(stmt.order_by(PerceptionSource.universe, PerceptionSource.name))
        return list(result.all())

    async def due_sources(self, now: datetime) -> list[PerceptionSource]:
        stmt = select(PerceptionSource).where(
            PerceptionSource.enabled.is_(True),
            (PerceptionSource.next_run_at.is_(None)) | (PerceptionSource.next_run_at <= now),
        )
        result = await self.session.scalars(stmt.order_by(PerceptionSource.next_run_at.nullsfirst(), PerceptionSource.name))
        return list(result.all())

    async def active_run(self, source_id: str) -> PerceptionRun | None:
        return await self.session.scalar(
            select(PerceptionRun).where(PerceptionRun.source_id == source_id, PerceptionRun.status == "running")
        )

    async def runs(self, source_id: str, *, limit: int = 50) -> list[PerceptionRun]:
        result = await self.session.scalars(
            select(PerceptionRun).where(PerceptionRun.source_id == source_id).order_by(PerceptionRun.started_at.desc()).limit(limit)
        )
        return list(result.all())

    async def add_source(self, item: PerceptionSource) -> PerceptionSource:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_run(self, item: PerceptionRun) -> PerceptionRun:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_notification(self, item: CreatorNotification) -> CreatorNotification:
        self.session.add(item)
        await self.session.flush()
        return item

    async def notification(self, notification_id: str, *, lock: bool = False) -> CreatorNotification | None:
        stmt = select(CreatorNotification).where(CreatorNotification.id == notification_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def recent_notification(self, actor_id: str, opportunity_id: str, since: datetime) -> CreatorNotification | None:
        return await self.session.scalar(
            select(CreatorNotification).where(
                CreatorNotification.recipient_actor_id == actor_id,
                CreatorNotification.opportunity_id == opportunity_id,
                CreatorNotification.created_at >= since,
            )
        )

    async def notifications(self, actor_id: str, *, status: str | None = None, limit: int = 50, offset: int = 0) -> list[CreatorNotification]:
        stmt = select(CreatorNotification).where(CreatorNotification.recipient_actor_id == actor_id)
        if status:
            stmt = stmt.where(CreatorNotification.status == status)
        result = await self.session.scalars(stmt.order_by(CreatorNotification.created_at.desc()).limit(limit).offset(offset))
        return list(result.all())

    async def opportunities_for_notification(self) -> list[Opportunity]:
        result = await self.session.scalars(
            select(Opportunity).where(Opportunity.status == "pending_creator_review").order_by(Opportunity.priority_score.desc())
        )
        return list(result.all())

    async def add_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str | None,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self.domain.add_event(event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id, payload)

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
