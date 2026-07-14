from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dispatch import DispatchItem
from app.models.entities import Agent, AgentCapability, Capability, Mission, Task
from app.models.execution import AgentExecution, AgentExecutionEvent


class ExecutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, value):
        self.session.add(value)
        await self.session.flush()
        return value

    async def get(self, execution_id: str, lock=False):
        stmt = select(AgentExecution).where(AgentExecution.id == execution_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, limit=100, offset=0):
        return list(
            (
                await self.session.scalars(
                    select(AgentExecution).order_by(AgentExecution.created_at, AgentExecution.id).limit(limit).offset(offset)
                )
            ).all()
        )

    async def events(self, execution_id: str):
        return list(
            (
                await self.session.scalars(
                    select(AgentExecutionEvent)
                    .where(AgentExecutionEvent.execution_id == execution_id)
                    .order_by(AgentExecutionEvent.sequence)
                )
            ).all()
        )

    async def next_event_sequence(self, execution_id: str):
        current = await self.session.scalar(
            select(func.max(AgentExecutionEvent.sequence)).where(AgentExecutionEvent.execution_id == execution_id)
        )
        return (current or 0) + 1

    async def dispatch(self, dispatch_id: str):
        return await self.session.get(DispatchItem, dispatch_id)

    async def mission(self, mission_id: str):
        return await self.session.get(Mission, mission_id)

    async def task(self, task_id: str):
        return await self.session.get(Task, task_id)

    async def agent(self, agent_id: str):
        return await self.session.get(Agent, agent_id)

    async def capability(self, capability_id: str):
        return await self.session.get(Capability, capability_id)

    async def agent_has_capability(self, agent_id: str, capability_id: str):
        return (
            await self.session.scalar(
                select(AgentCapability).where(
                    AgentCapability.agent_id == agent_id, AgentCapability.capability_id == capability_id
                )
            )
            is not None
        )

    async def commit(self):
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
