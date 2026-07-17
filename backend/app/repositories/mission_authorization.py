from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Mission
from app.models.mission_authorization import MissionAuthorization
from app.repositories.domain import DomainRepository


class MissionAuthorizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def mission(self, mission_id: str, *, lock: bool = False) -> Mission | None:
        stmt = select(Mission).where(Mission.id == mission_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def active_for_mission(self, mission_id: str, *, lock: bool = False) -> MissionAuthorization | None:
        stmt = select(MissionAuthorization).where(
            MissionAuthorization.mission_id == mission_id,
            MissionAuthorization.status.in_(("pending", "authorized", "suspended")),
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def latest_for_mission(self, mission_id: str) -> MissionAuthorization | None:
        return await self.session.scalar(
            select(MissionAuthorization).where(MissionAuthorization.mission_id == mission_id).order_by(MissionAuthorization.created_at.desc()).limit(1)
        )

    async def add(self, item: MissionAuthorization) -> MissionAuthorization:
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
        await self.domain.add_event(event_type, "mission_authorization", aggregate_id, actor_id, actor_role, correlation_id, payload)

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
