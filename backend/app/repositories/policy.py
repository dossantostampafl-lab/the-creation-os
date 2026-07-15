from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation import MissionConsolidation
from app.models.decision import MissionDecision
from app.models.entities import Mission
from app.models.policy import MissionDecisionReasoning


class PolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mission(self, mission_id: str, *, lock: bool = False) -> Mission | None:
        statement = select(Mission).where(Mission.id == mission_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def decision(self, mission_id: str) -> MissionDecision | None:
        return await self.session.scalar(select(MissionDecision).where(MissionDecision.mission_id == mission_id))

    async def active_decision_count(self, mission_id: str) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(MissionDecision).where(MissionDecision.mission_id == mission_id)) or 0)

    async def consolidation(self, decision: MissionDecision) -> MissionConsolidation | None:
        if decision.consolidation_id is not None:
            return await self.session.get(MissionConsolidation, decision.consolidation_id)
        return await self.session.scalar(
            select(MissionConsolidation).where(MissionConsolidation.mission_id == decision.mission_id)
        )

    async def reasoning_for_decision(self, decision_id: str) -> MissionDecisionReasoning | None:
        return await self.session.scalar(
            select(MissionDecisionReasoning).where(MissionDecisionReasoning.decision_id == decision_id)
        )

    async def reasoning_for_mission(self, mission_id: str) -> MissionDecisionReasoning | None:
        return await self.session.scalar(
            select(MissionDecisionReasoning)
            .join(MissionDecision, MissionDecisionReasoning.decision_id == MissionDecision.id)
            .where(MissionDecision.mission_id == mission_id)
        )

    async def add(self, item: MissionDecisionReasoning) -> MissionDecisionReasoning:
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
