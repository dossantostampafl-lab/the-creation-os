from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rockmam import RockmamPossibilityAssessment
from app.models.sophia import SophiaUnderstanding
from app.repositories.domain import DomainRepository


class RockmamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def understanding(self, understanding_id: str, *, lock: bool = False) -> SophiaUnderstanding | None:
        statement = select(SophiaUnderstanding).where(SophiaUnderstanding.id == understanding_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def assessment(self, understanding_id: str) -> RockmamPossibilityAssessment | None:
        return await self.session.scalar(
            select(RockmamPossibilityAssessment).where(
                RockmamPossibilityAssessment.sophia_understanding_id == understanding_id
            )
        )

    async def add(self, item: RockmamPossibilityAssessment) -> RockmamPossibilityAssessment:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_event(
        self,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict,
    ) -> None:
        await self.domain.add_event(
            "rockmam_possibility_assessment_created",
            "sophia_understanding",
            aggregate_id,
            actor_id,
            actor_role,
            correlation_id,
            payload,
        )

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
