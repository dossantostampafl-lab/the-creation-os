from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dispatch import DispatchAttempt, DispatchItem
from app.models.entities import Capability, Mission, Task, TaskDependency
from app.repositories.domain import DomainRepository


class DispatchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def task(self, task_id):
        return await self.session.get(Task, task_id)

    async def mission(self, mission_id, lock=False):
        if lock:
            return await self.session.scalar(select(Mission).where(Mission.id == mission_id).with_for_update())
        return await self.session.get(Mission, mission_id)

    async def capability(self, capability_id):
        return await self.session.get(Capability, capability_id)

    async def add(self, item):
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, item_id, lock=False):
        stmt = select(DispatchItem).where(DispatchItem.id == item_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, mission_id=None, state=None, limit=100, offset=0):
        stmt = select(DispatchItem)
        if mission_id:
            stmt = stmt.where(DispatchItem.mission_id == mission_id)
        if state:
            stmt = stmt.where(DispatchItem.state == state)
        stmt = stmt.order_by(
            DispatchItem.priority.desc(), DispatchItem.available_at, DispatchItem.created_at, DispatchItem.id
        ).limit(limit).offset(offset)
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

    async def acquire(self, now, capability_ids=None):
        stmt = (
            select(DispatchItem)
            .where(DispatchItem.state.in_(("queued", "retry_scheduled")), DispatchItem.available_at <= now)
            .order_by(DispatchItem.priority.desc(), DispatchItem.available_at, DispatchItem.created_at, DispatchItem.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if capability_ids is not None:
            stmt = stmt.where(DispatchItem.capability_id.in_(capability_ids))
        return await self.session.scalar(stmt)

    async def attempts(self, item_id):
        return list(
            (
                await self.session.scalars(
                    select(DispatchAttempt)
                    .where(DispatchAttempt.dispatch_item_id == item_id)
                    .order_by(DispatchAttempt.created_at, DispatchAttempt.id)
                )
            ).all()
        )

    async def expired_leases(self, now):
        stmt = (
            select(DispatchItem)
            .where(DispatchItem.state == "leased", DispatchItem.lease_expires_at < now)
            .order_by(DispatchItem.lease_expires_at, DispatchItem.id)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(stmt)).all())

    async def commit(self):
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self):
        await self.session.rollback()

    async def add_event(self, event_type, mission_id, actor_id, actor_role, correlation_id, payload=None, causation_id=None):
        return await DomainRepository(self.session).add_event(
            event_type, "mission", mission_id, actor_id, actor_role, correlation_id, payload, causation_id=causation_id
        )
