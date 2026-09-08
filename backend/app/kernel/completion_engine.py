from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.domain import MissionStatus, transition
from app.kernel.completion import completion_target
from app.models.entities import Mission, Task
from app.repositories.domain import DomainRepository


class MissionCompletionEngine:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def evaluate(self, mission_id: str, correlation_id: str) -> MissionStatus | None:
        async with self.session_factory() as session:
            repository = DomainRepository(session)
            mission = await repository.get_for_update(Mission, mission_id)
            if mission is None:
                raise ValueError("Mission not found")
            current = MissionStatus(mission.status)
            if current != MissionStatus.EXECUTING:
                return None

            tasks = list((await session.scalars(
                select(Task).where(Task.mission_id == mission_id).order_by(Task.created_at, Task.id)
            )).all())
            target = completion_target([task.status for task in tasks])
            if target not in {MissionStatus.MANIFESTED, MissionStatus.FAILED}:
                return target

            mission.status = transition("mission", current, target)
            mission.completed_at = datetime.now(timezone.utc)
            await repository.add_event(
                "mission_manifested" if target is MissionStatus.MANIFESTED else "mission_failed",
                "mission",
                mission.id,
                "system",
                "completion_engine",
                correlation_id,
                {"task_statuses": [task.status for task in tasks]},
            )
            await repository.commit()
            return target
