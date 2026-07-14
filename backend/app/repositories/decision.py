from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation import MissionConsolidation
from app.models.decision import MissionDecision
from app.models.entities import Mission


class DecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mission(self, mission_id: str, *, lock: bool = False) -> Mission | None:
        statement = select(Mission).where(Mission.id == mission_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def consolidation(self, mission_id: str) -> MissionConsolidation | None:
        return await self.session.scalar(
            select(MissionConsolidation).where(MissionConsolidation.mission_id == mission_id)
        )

    async def decision(self, mission_id: str) -> MissionDecision | None:
        return await self.session.scalar(select(MissionDecision).where(MissionDecision.mission_id == mission_id))

    async def add(self, item: MissionDecision) -> MissionDecision:
        self.session.add(item)
        await self.session.flush()
        return item

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
