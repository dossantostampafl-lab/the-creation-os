from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationExecution
from app.repositories.domain import DomainRepository


class AutomationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)

    async def execution(self, creator_id: str, connector_id: str, idempotency_key: str) -> AutomationExecution | None:
        return await self.session.scalar(
            select(AutomationExecution).where(
                AutomationExecution.creator_id == creator_id,
                AutomationExecution.connector_id == connector_id,
                AutomationExecution.idempotency_key == idempotency_key,
            )
        )

    async def add(self, item: AutomationExecution) -> AutomationExecution:
        self.session.add(item)
        await self.session.flush()
        return item

    async def add_event(
        self,
        aggregate_id: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
        payload: dict,
    ) -> None:
        await self.domain.add_event(
            "automation_connector_executed",
            "automation_execution",
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
