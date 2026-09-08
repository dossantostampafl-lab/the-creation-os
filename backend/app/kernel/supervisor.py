from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.domain import MissionStatus, transition
from app.models.entities import Mission
from app.repositories.domain import DomainRepository


class MissionRuntimeSupervisor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def start_execution(self, mission_id: str, correlation_id: str) -> bool:
        async with self.session_factory() as session:
            repository = DomainRepository(session)
            mission = await repository.get_for_update(Mission, mission_id)
            if mission is None:
                raise ValueError("Mission not found")
            current = MissionStatus(mission.status)
            if current == MissionStatus.EXECUTING:
                return False
            if current != MissionStatus.DISTRIBUTED:
                return False
            mission.status = transition("mission", current, MissionStatus.EXECUTING)
            mission.started_at = mission.started_at or datetime.now(timezone.utc)
            await repository.add_event(
                "mission_execution_started",
                "mission",
                mission.id,
                "system",
                "mission_runtime_supervisor",
                correlation_id,
            )
            await repository.commit()
            return True
