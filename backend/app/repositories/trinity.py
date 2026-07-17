from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.god import GodConversationInteraction
from app.models.rockmam import RockmamPossibilityAssessment
from app.models.sophia import SophiaUnderstanding
from app.repositories.domain import DomainRepository


class TrinityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def god_interaction(self, interaction_id: str, *, lock: bool = False) -> GodConversationInteraction | None:
        statement = select(GodConversationInteraction).where(GodConversationInteraction.id == interaction_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def understanding(self, god_interaction_id: str) -> SophiaUnderstanding | None:
        return await self.session.scalar(
            select(SophiaUnderstanding).where(SophiaUnderstanding.god_interaction_id == god_interaction_id)
        )

    async def assessment(self, sophia_understanding_id: str) -> RockmamPossibilityAssessment | None:
        return await self.session.scalar(
            select(RockmamPossibilityAssessment).where(
                RockmamPossibilityAssessment.sophia_understanding_id == sophia_understanding_id
            )
        )

    async def add_understanding(self, item: SophiaUnderstanding) -> SophiaUnderstanding:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_assessment(self, item: RockmamPossibilityAssessment) -> RockmamPossibilityAssessment:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict,
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
