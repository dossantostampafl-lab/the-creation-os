from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation import MissionConsolidation
from app.models.dispatch import DispatchItem
from app.models.entities import Mission, Task, TaskDependency
from app.models.execution import AgentExecution
from app.repositories.domain import DomainRepository


class ConsolidationRepository:
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

    async def tasks(self, mission_id: str) -> list[Task]:
        return list(
            (
                await self.session.scalars(
                    select(Task).where(Task.mission_id == mission_id).order_by(Task.id)
                )
            ).all()
        )

    async def dependencies(self, task_ids: set[str]) -> list[TaskDependency]:
        if not task_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(TaskDependency)
                    .where(
                        or_(
                            TaskDependency.task_id.in_(task_ids),
                            TaskDependency.dependency_id.in_(task_ids),
                        )
                    )
                    .order_by(TaskDependency.task_id, TaskDependency.dependency_id)
                )
            ).all()
        )

    async def dispatch_items(self, mission_id: str, task_ids: set[str]) -> list[DispatchItem]:
        conditions = [DispatchItem.mission_id == mission_id]
        if task_ids:
            conditions.append(DispatchItem.task_id.in_(task_ids))
        return list(
            (
                await self.session.scalars(
                    select(DispatchItem).where(or_(*conditions)).order_by(DispatchItem.id)
                )
            ).all()
        )

    async def executions(
        self,
        mission_id: str,
        task_ids: set[str],
        dispatch_ids: set[str],
    ) -> list[AgentExecution]:
        conditions = [AgentExecution.mission_id == mission_id]
        if task_ids:
            conditions.append(AgentExecution.task_id.in_(task_ids))
        if dispatch_ids:
            conditions.append(AgentExecution.dispatch_item_id.in_(dispatch_ids))
        return list(
            (
                await self.session.scalars(
                    select(AgentExecution).where(or_(*conditions)).order_by(AgentExecution.id)
                )
            ).all()
        )

    async def add(self, item: MissionConsolidation) -> MissionConsolidation:
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
