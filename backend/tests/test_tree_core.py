from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.entities import Agent, Capability
from app.services.tree_core import HEARTBEAT_TTL, TreeCoreError, TreeCoreService


class FakeTreeCoreRepository:
    def __init__(self) -> None:
        self.agent_items: dict[str, Agent] = {}
        self.capability_items: dict[str, Capability] = {}
        self.mission_items = {}

    async def add(self, entity):
        entity.id = entity.id or str(uuid.uuid4())
        if isinstance(entity, Agent):
            entity.capabilities = []
            now = datetime.now(timezone.utc)
            entity.created_at = entity.updated_at = now
            self.agent_items[entity.id] = entity
        else:
            self.capability_items[entity.id] = entity
        return entity

    async def agent(self, agent_id):
        return self.agent_items.get(agent_id)

    async def agent_for_update(self, agent_id):
        return self.agent_items.get(agent_id)

    async def agents(self):
        return sorted(self.agent_items.values(), key=lambda item: (item.name, item.id))

    async def capability(self, capability_id):
        return self.capability_items.get(capability_id)

    async def capability_by_name(self, name):
        return next((item for item in self.capability_items.values() if item.name.lower() == name.lower()), None)

    async def capabilities(self):
        return sorted(self.capability_items.values(), key=lambda item: item.name)

    async def mission(self, mission_id):
        return self.mission_items.get(mission_id)

    async def eligible_agents(self, capability_names, heartbeat_cutoff):
        result = []
        for agent in self.agent_items.values():
            names = {item.name.lower() for item in agent.capabilities}
            if (agent.enabled and agent.status == "idle" and agent.heartbeat_at
                    and agent.heartbeat_at >= heartbeat_cutoff and capability_names <= names):
                result.append(agent)
        return sorted(result, key=lambda item: (-item.priority, item.name, item.id))

    async def commit(self):
        return None


@pytest.fixture
def tree_core():
    repository = FakeTreeCoreRepository()
    return TreeCoreService(repository), repository


async def registered(service, name="Agent", priority=0, enabled=True):
    return await service.register_agent(name, "Registry agent", "central", priority, enabled)


@pytest.mark.asyncio
async def test_register_agent(tree_core):
    service, _ = tree_core
    agent = await registered(service)
    assert (agent.name, agent.universe_name, agent.status, agent.version) == ("Agent", "central", "offline", 1)


@pytest.mark.asyncio
async def test_register_capability(tree_core):
    service, _ = tree_core
    capability = await service.create_capability("planning", "Plans work")
    assert [item.name for item in await service.list_capabilities()] == [capability.name]


@pytest.mark.asyncio
async def test_heartbeat_marks_enabled_agent_idle(tree_core):
    service, _ = tree_core
    agent = await registered(service)
    now = datetime.now(timezone.utc)
    await service.heartbeat(agent.id, now)
    assert agent.status == "idle" and agent.heartbeat_at == now


@pytest.mark.asyncio
async def test_enable_agent(tree_core):
    service, _ = tree_core
    agent = await registered(service, enabled=False)
    await service.enable(agent.id)
    assert agent.enabled and agent.status == "offline"


@pytest.mark.asyncio
async def test_disable_agent(tree_core):
    service, _ = tree_core
    agent = await registered(service)
    await service.disable(agent.id)
    assert not agent.enabled and agent.status == "disabled"


async def match_fixture(service, repository, priorities=(1,)):
    capability = await service.create_capability("analysis", "Analyzes")
    agents = []
    now = datetime.now(timezone.utc)
    for index, priority in enumerate(priorities):
        agent = await registered(service, f"Agent {index}", priority)
        await service.add_capability(agent.id, capability.id)
        await service.heartbeat(agent.id, now)
        agents.append(agent)
    mission = SimpleNamespace(id=str(uuid.uuid4()), status="authorized")
    repository.mission_items[mission.id] = mission
    return mission, agents, now


@pytest.mark.asyncio
async def test_match_by_capability(tree_core):
    service, repository = tree_core
    mission, agents, now = await match_fixture(service, repository)
    _, matches = await service.match(mission.id, ["analysis"], now)
    assert matches == agents


@pytest.mark.asyncio
async def test_match_orders_by_priority(tree_core):
    service, repository = tree_core
    mission, agents, now = await match_fixture(service, repository, (1, 10, 5))
    _, matches = await service.match(mission.id, ["analysis"], now)
    assert [item.priority for item in matches] == [10, 5, 1]


@pytest.mark.asyncio
async def test_match_rejects_expired_heartbeat(tree_core):
    service, repository = tree_core
    mission, agents, now = await match_fixture(service, repository)
    agents[0].heartbeat_at = now - HEARTBEAT_TTL - timedelta(seconds=1)
    assert (await service.match(mission.id, ["analysis"], now))[1] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["offline", "disabled"])
async def test_match_rejects_ineligible_status(tree_core, state):
    service, repository = tree_core
    mission, agents, now = await match_fixture(service, repository)
    agents[0].status = state
    if state == "disabled":
        agents[0].enabled = False
    assert (await service.match(mission.id, ["analysis"], now))[1] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["drafted", "planned", "validated", "cancelled", "failed", "manifested"])
async def test_match_rejects_every_non_authorized_mission(tree_core, state):
    service, repository = tree_core
    mission = SimpleNamespace(id=str(uuid.uuid4()), status=state)
    repository.mission_items[mission.id] = mission
    with pytest.raises(TreeCoreError, match="authorized Missions"):
        await service.match(mission.id, ["analysis"])


@pytest.mark.asyncio
async def test_match_is_read_only_and_rejects_incompatible_capability(tree_core):
    service, repository = tree_core
    mission, agents, now = await match_fixture(service, repository)
    snapshot = (mission.status, agents[0].status, agents[0].version, len(repository.mission_items))
    assert (await service.match(mission.id, ["missing"], now))[1] == []
    assert (mission.status, agents[0].status, agents[0].version, len(repository.mission_items)) == snapshot


@pytest.mark.asyncio
async def test_duplicate_agent_capability_is_blocked(tree_core):
    service, repository = tree_core
    _, agents, _ = await match_fixture(service, repository)
    capability = next(iter(repository.capability_items.values()))
    with pytest.raises(TreeCoreError, match="already assigned"):
        await service.add_capability(agents[0].id, capability.id)


@pytest.mark.asyncio
async def test_capability_name_is_normalized_and_duplicate_blocked(tree_core):
    service, _ = tree_core
    capability = await service.create_capability("  Analysis  ", "first")
    assert capability.name == "analysis"
    with pytest.raises(TreeCoreError, match="already exists"):
        await service.create_capability("ANALYSIS", "duplicate")
