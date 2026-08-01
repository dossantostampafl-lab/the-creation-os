from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.core.domain import DomainError
from app.models.entities import Agent, Capability, Mission
from app.repositories.tree_core import TreeCoreRepository
from app.services.domain import NotFoundError

HEARTBEAT_TTL = timedelta(minutes=5)


class TreeCoreError(DomainError):
    pass


class TreeCoreService:
    def __init__(self, repository: TreeCoreRepository) -> None:
        self.repository = repository

    async def _commit(self, conflict: str) -> None:
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            raise TreeCoreError(conflict) from exc

    async def _mutable_agent(self, agent_id: str) -> Agent:
        agent = await self.repository.agent_for_update(agent_id)
        if agent is None:
            raise NotFoundError("Agent not found")
        return agent

    async def register_agent(self, name: str, description: str, universe: str, priority: int, enabled: bool) -> Agent:
        agent = Agent(
            name=name.strip(), description=description, universe_name=universe.strip(), priority=priority,
            enabled=enabled, active=enabled, status="offline" if enabled else "disabled", version=1,
            capabilities_json={},
        )
        await self.repository.add(agent)
        await self._commit("Agent conflicts with an existing registry entry")
        return await self.get_agent(agent.id)

    async def update_agent(self, agent_id: str, **changes) -> Agent:
        agent = await self._mutable_agent(agent_id)
        mapping = {"universe": "universe_name"}
        for field, value in changes.items():
            if value is not None:
                setattr(agent, mapping.get(field, field), value.strip() if isinstance(value, str) else value)
        agent.version += 1
        await self._commit("Agent update conflict")
        return await self.get_agent(agent.id)

    async def heartbeat(self, agent_id: str, now: datetime | None = None) -> Agent:
        agent = await self._mutable_agent(agent_id)
        if not agent.enabled:
            raise TreeCoreError("Disabled agent cannot send heartbeat")
        agent.heartbeat_at = now or datetime.now(timezone.utc)
        agent.status = "idle"
        agent.version += 1
        await self._commit("Agent heartbeat conflict")
        return await self.get_agent(agent.id)

    async def enable(self, agent_id: str) -> Agent:
        agent = await self._mutable_agent(agent_id)
        agent.enabled = agent.active = True
        agent.status = "offline"
        agent.version += 1
        await self._commit("Agent enable conflict")
        return await self.get_agent(agent.id)

    async def disable(self, agent_id: str) -> Agent:
        agent = await self._mutable_agent(agent_id)
        agent.enabled = agent.active = False
        agent.status = "disabled"
        agent.version += 1
        await self._commit("Agent disable conflict")
        return await self.get_agent(agent.id)

    async def create_capability(self, name: str, description: str) -> Capability:
        normalized = name.strip().lower()
        if await self.repository.capability_by_name(normalized):
            raise TreeCoreError("Capability already exists")
        capability = Capability(name=normalized, description=description)
        await self.repository.add(capability)
        await self._commit("Capability already exists")
        return capability

    async def add_capability(self, agent_id: str, capability_id: str) -> Agent:
        agent = await self._mutable_agent(agent_id)
        capability = await self.repository.capability(capability_id)
        if capability is None:
            raise NotFoundError("Capability not found")
        if any(item.id == capability.id for item in agent.capabilities):
            raise TreeCoreError("Capability is already assigned to agent")
        agent.capabilities.append(capability)
        agent.version += 1
        await self._commit("Capability is already assigned to agent")
        return await self.get_agent(agent.id)

    async def remove_capability(self, agent_id: str, capability_id: str) -> Agent:
        agent = await self._mutable_agent(agent_id)
        capability = next((item for item in agent.capabilities if item.id == capability_id), None)
        if capability is None:
            raise NotFoundError("Capability not assigned to agent")
        agent.capabilities.remove(capability)
        agent.version += 1
        await self._commit("Capability removal conflict")
        return await self.get_agent(agent.id)

    async def list_agents(self) -> list[Agent]:
        return await self.repository.agents()

    async def get_agent(self, agent_id: str) -> Agent:
        agent = await self.repository.agent(agent_id)
        if agent is None:
            raise NotFoundError("Agent not found")
        return agent

    async def list_capabilities(self) -> list[Capability]:
        return await self.repository.capabilities()

    async def match(self, mission_id: str, required_capabilities: list[str], now: datetime | None = None) -> tuple[Mission, list[Agent]]:
        mission = await self.repository.mission(mission_id)
        if mission is None:
            raise NotFoundError("Mission not found")
        if mission.status not in {"authorized", "distributed", "executing"}:
            raise TreeCoreError("Tree Core only matches authorized, distributed, or executing Missions")
        required = {name.strip().lower() for name in required_capabilities if name.strip()}
        if not required:
            raise TreeCoreError("At least one capability is required")
        current = now or datetime.now(timezone.utc)
        return mission, await self.repository.eligible_agents(required, current - HEARTBEAT_TTL)
