from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Agent, Capability, Mission, Universe


class TreeCoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, entity):
        self.session.add(entity)
        return entity

    async def universe_by_code(self, code: str) -> Universe | None:
        return await self.session.scalar(select(Universe).where(func.lower(Universe.code) == code.lower()))

    async def agent(self, agent_id: str) -> Agent | None:
        return await self.session.scalar(
            select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.capabilities))
        )

    async def agent_for_update(self, agent_id: str) -> Agent | None:
        return await self.session.scalar(
            select(Agent).where(Agent.id == agent_id).with_for_update().options(selectinload(Agent.capabilities))
        )

    async def agents(self) -> list[Agent]:
        result = await self.session.scalars(
            select(Agent).options(selectinload(Agent.capabilities)).order_by(Agent.name, Agent.id)
        )
        return list(result.unique().all())

    async def capability(self, capability_id: str) -> Capability | None:
        return await self.session.get(Capability, capability_id)

    async def capability_by_name(self, name: str) -> Capability | None:
        return await self.session.scalar(select(Capability).where(func.lower(Capability.name) == name.lower()))

    async def capabilities(self) -> list[Capability]:
        return list((await self.session.scalars(select(Capability).order_by(Capability.name))).all())

    async def mission(self, mission_id: str) -> Mission | None:
        return await self.session.get(Mission, mission_id)

    async def eligible_agents(self, capability_names: set[str], heartbeat_cutoff: datetime) -> list[Agent]:
        normalized = {name.lower() for name in capability_names}
        stmt = (
            select(Agent)
            .join(Agent.capabilities)
            .outerjoin(Universe, Agent.universe_id == Universe.id)
            .where(
                Agent.enabled.is_(True),
                Agent.status == "idle",
                Agent.heartbeat_at.is_not(None),
                Agent.heartbeat_at >= heartbeat_cutoff,
                func.lower(Capability.name).in_(normalized),
                # Agents not linked to a governed Universe (universe_id NULL — the
                # common case for pre-Lote-2.6 Agents/fixtures using an arbitrary
                # free-text universe_name) stay eligible exactly as before. Only
                # Agents actually linked to one of the 12 registered Universes are
                # gated by that Universe's active flag.
                or_(Agent.universe_id.is_(None), Universe.active.is_(True)),
            )
            .group_by(Agent.id)
            .having(func.count(func.distinct(func.lower(Capability.name))) == len(normalized))
            .options(selectinload(Agent.capabilities))
            .order_by(Agent.priority.desc(), Agent.name, Agent.id)
        )
        result = await self.session.scalars(stmt)
        return list(result.unique().all())

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
