from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability_registry import RegisteredCapability
from app.repositories.domain import DomainRepository


class CapabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def by_capability_id(self, capability_id: str, *, lock: bool = False) -> RegisteredCapability | None:
        statement = select(RegisteredCapability).where(RegisteredCapability.capability_id == capability_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list(self) -> list[RegisteredCapability]:
        result = await self.session.scalars(select(RegisteredCapability).order_by(RegisteredCapability.capability_id))
        return list(result.all())

    async def add(self, item: RegisteredCapability) -> RegisteredCapability:
        self.session.add(item)
        await self.session.flush()
        return item

    async def flush(self) -> None:
        await self.session.flush()

    async def add_event(
        self,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict,
    ) -> None:
        await self.domain.add_event(
            "capability_state_changed",
            "registered_capability",
            aggregate_id,
            actor_id,
            actor_role,
            correlation_id,
            payload,
        )

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
