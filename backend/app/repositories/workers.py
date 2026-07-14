from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dispatch import DispatchItem, Worker
from app.models.entities import Capability


class WorkerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, value):
        self.session.add(value)
        await self.session.flush()
        return value

    async def capability(self, name: str):
        return await self.session.scalar(select(Capability).where(Capability.name == name))

    async def get_by_uuid(self, worker_uuid: str, lock=False):
        stmt = select(Worker).options(selectinload(Worker.capabilities)).where(Worker.worker_uuid == worker_uuid)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get(self, worker_id: str):
        return await self.session.scalar(
            select(Worker).options(selectinload(Worker.capabilities)).where(Worker.id == worker_id)
        )

    async def list(self):
        return list(
            (await self.session.scalars(select(Worker).options(selectinload(Worker.capabilities)).order_by(Worker.registered_at, Worker.id))).all()
        )

    async def active_lease(self, worker_uuid: str):
        return await self.session.scalar(
            select(DispatchItem).where(DispatchItem.lease_owner == worker_uuid, DispatchItem.state == "leased").with_for_update()
        )

    async def commit(self):
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
