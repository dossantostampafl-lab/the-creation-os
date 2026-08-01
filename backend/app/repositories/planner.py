from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Capability, Mission, Task, TaskDependency
from app.repositories.domain import DomainRepository


class PlannerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.events = DomainRepository(session)

    async def mission(self, mission_id, lock=False):
        stmt = select(Mission).where(Mission.id == mission_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def capability(self, capability_id):
        return await self.session.get(Capability, capability_id)

    async def task(self, task_id, lock=False):
        stmt = select(Task).where(Task.id == task_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def add(self, item):
        self.session.add(item)
        await self.session.flush()
        return item

    async def tasks(self, mission_id):
        return list(
            (await self.session.scalars(select(Task).where(Task.mission_id == mission_id).order_by(Task.priority.desc(), Task.id))).all()
        )

    async def dependencies(self, mission_id):
        stmt = select(TaskDependency).join(Task, Task.id == TaskDependency.task_id).where(Task.mission_id == mission_id)
        return list((await self.session.scalars(stmt)).all())

    async def dependencies_ready(self, task_id):
        deps = list(
            (
                await self.session.scalars(
                    select(Task).join(TaskDependency, Task.id == TaskDependency.dependency_id).where(TaskDependency.task_id == task_id)
                )
            ).all()
        )
        return all(item.state == "completed" for item in deps)

    async def delete_dependency(self, task_id, dependency_id):
        item = await self.session.get(TaskDependency, (task_id, dependency_id))
        if item:
            await self.session.delete(item)
        return item

    async def commit(self):
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self):
        await self.session.rollback()

    async def add_event(self, **kwargs):
        return await self.events.add_event(**kwargs)
