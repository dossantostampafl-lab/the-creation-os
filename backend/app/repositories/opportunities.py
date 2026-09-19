from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Conversation, Inception, Message
from app.models.opportunity import Opportunity, OpportunityEvidence, OpportunityObservation
from app.repositories.domain import DomainRepository


class OpportunityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def observation_by_fingerprint(self, fingerprint: str) -> OpportunityObservation | None:
        return await self.session.scalar(select(OpportunityObservation).where(OpportunityObservation.observation_fingerprint == fingerprint))

    async def add_observation(self, item: OpportunityObservation) -> OpportunityObservation:
        self.session.add(item)
        await self.session.flush()
        return item

    async def observations(
        self,
        *,
        universe: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OpportunityObservation]:
        stmt = select(OpportunityObservation)
        if universe:
            stmt = stmt.where(OpportunityObservation.universe == universe)
        result = await self.session.scalars(stmt.order_by(OpportunityObservation.created_at.desc()).limit(limit).offset(offset))
        return list(result.all())

    async def observations_for_discovery(self, enabled_universes: set[str]) -> list[OpportunityObservation]:
        stmt = select(OpportunityObservation).where(OpportunityObservation.universe.in_(sorted(enabled_universes)))
        result = await self.session.scalars(stmt.order_by(OpportunityObservation.observed_at.desc()))
        return list(result.all())

    async def opportunity(self, opportunity_id: str, *, lock: bool = False) -> Opportunity | None:
        stmt = select(Opportunity).where(Opportunity.id == opportunity_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def opportunity_by_correlation(self, correlation_key: str) -> Opportunity | None:
        return await self.session.scalar(
            select(Opportunity).where(
                Opportunity.correlation_key == correlation_key,
                Opportunity.status.in_(["detected", "under_analysis", "pending_creator_review"]),
            )
        )

    async def add_opportunity(self, item: Opportunity) -> Opportunity:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_evidence(self, opportunity_id: str, observation_id: str) -> None:
        exists = await self.session.get(OpportunityEvidence, {"opportunity_id": opportunity_id, "observation_id": observation_id})
        if exists is None:
            self.session.add(OpportunityEvidence(opportunity_id=opportunity_id, observation_id=observation_id))
            await self.session.flush()

    async def opportunities(
        self,
        *,
        universe: str | None = None,
        status: str | None = None,
        min_priority: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Opportunity]:
        stmt = select(Opportunity)
        if universe:
            stmt = stmt.where(Opportunity.universe == universe)
        if status:
            stmt = stmt.where(Opportunity.status == status)
        if min_priority is not None:
            stmt = stmt.where(Opportunity.priority_score >= min_priority)
        result = await self.session.scalars(stmt.order_by(Opportunity.priority_score.desc(), Opportunity.detected_at.desc()).limit(limit).offset(offset))
        return list(result.all())

    async def expirable(self, now: datetime) -> list[Opportunity]:
        result = await self.session.scalars(
            select(Opportunity).where(
                Opportunity.expires_at <= now,
                Opportunity.status.in_(["detected", "under_analysis", "pending_creator_review"]),
            )
        )
        return list(result.all())

    async def add_conversation(self, item: Conversation) -> Conversation:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_message(self, item: Message) -> Message:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_inception(self, item: Inception) -> Inception:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_event(
        self,
        event_type: str,
        aggregate_id: str | None,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self.domain.add_event(event_type, "opportunity", aggregate_id, actor_id, actor_role, correlation_id, payload)

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
