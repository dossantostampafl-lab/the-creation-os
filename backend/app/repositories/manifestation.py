from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision import MissionDecision
from app.models.entities import Mission
from app.models.manifestation import MissionManifestation
from app.repositories.domain import DomainRepository


class ManifestationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mission(self, mission_id: str, *, lock: bool = False) -> Mission | None:
        statement = select(Mission).where(Mission.id == mission_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def decision(self, mission_id: str) -> MissionDecision | None:
        return await self.session.scalar(select(MissionDecision).where(MissionDecision.mission_id == mission_id))

    async def manifestation(self, mission_id: str) -> MissionManifestation | None:
        return await self.session.scalar(select(MissionManifestation).where(MissionManifestation.mission_id == mission_id))

    async def add(self, item: MissionManifestation) -> MissionManifestation:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_event(self, event_type, mission_id, actor_id, actor_role, correlation_id, payload=None, causation_id=None):
        return await DomainRepository(self.session).add_event(
            event_type, "mission", mission_id, actor_id, actor_role, correlation_id, payload, causation_id=causation_id
        )

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
