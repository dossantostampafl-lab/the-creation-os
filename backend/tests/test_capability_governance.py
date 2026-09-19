from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.automation.contracts import ConnectorCapability
from app.automation.registry import ConnectorRegistry
from app.capabilities.contracts import CapabilityDefinition, CapabilityPermission
from app.capabilities.registry import CapabilityRegistry
from app.core.domain import Actor
from app.models.capability_registry import RegisteredCapability
from app.services.capability_governance import (
    CAPABILITY_DEPENDENCY_CYCLE,
    CAPABILITY_DEPENDENCY_DISABLED,
    CAPABILITY_DISABLED,
    CAPABILITY_PERMISSION_DENIED,
    CONNECTOR_UNAVAILABLE,
    CapabilityGovernanceService,
)


class EchoConnector:
    connector_id = "echo"

    def capabilities(self) -> list[ConnectorCapability]:
        return [ConnectorCapability(name="echo", description="Echo", input_schema={})]


class FakeGovernanceRepository:
    def __init__(self) -> None:
        self.items: dict[str, RegisteredCapability] = {}
        self.events: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0

    async def by_capability_id(self, capability_id: str, *, lock: bool = False) -> RegisteredCapability | None:
        return self.items.get(capability_id)

    async def list(self) -> list[RegisteredCapability]:
        return [self.items[key] for key in sorted(self.items)]

    async def add(self, item: RegisteredCapability) -> RegisteredCapability:
        item.id = item.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        item.created_at = item.created_at or now
        item.updated_at = item.updated_at or now
        self.items[item.capability_id] = item
        return item

    async def flush(self) -> None:
        return None

    async def add_event(self, aggregate_id: str, actor_id: str, actor_role: str, correlation_id: str, payload: dict, event_type: str = "capability_state_changed") -> None:
        self.events.append((event_type, payload))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def capability_registry(*definitions: CapabilityDefinition) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry


def connector_registry(available: bool = True) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    if available:
        registry.register(EchoConnector())  # type: ignore[arg-type]
    return registry


def definition(
    capability_id: str,
    *,
    connector_capability: str = "echo",
    enabled: bool = True,
    dependencies: tuple[str, ...] = (),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        name=capability_id,
        description=f"{capability_id} description",
        version="1.0.0",
        connector_id="echo",
        connector_capability=connector_capability,
        enabled=enabled,
        permissions=(CapabilityPermission.READ,),
        dependencies=dependencies,
    )


def service(registry: CapabilityRegistry, connectors: ConnectorRegistry | None = None) -> tuple[CapabilityGovernanceService, FakeGovernanceRepository]:
    repository = FakeGovernanceRepository()
    return (
        CapabilityGovernanceService(
            repository,  # type: ignore[arg-type]
            capability_registry=registry,
            connector_registry=connectors or connector_registry(),
        ),
        repository,
    )


@pytest.mark.asyncio
async def test_disabled_capability_does_not_authorize():
    governance, repository = service(capability_registry(definition("test.echo", enabled=False)))

    with pytest.raises(CAPABILITY_DISABLED):
        await governance.authorize_execution(Actor("creator-1", "creator"), connector_id="echo", connector_capability="echo", correlation_id="c")

    assert repository.events[-1][0] == "capability.execution.denied"
    assert repository.events[-1][1]["code"] == "CAPABILITY_DISABLED"


@pytest.mark.asyncio
async def test_disabled_direct_dependency_blocks_execution():
    governance, repository = service(
        capability_registry(
            definition("test.base", connector_capability="base", enabled=False),
            definition("test.echo", dependencies=("test.base",)),
        )
    )

    with pytest.raises(CAPABILITY_DEPENDENCY_DISABLED):
        await governance.authorize_execution(Actor("creator-1", "creator"), connector_id="echo", connector_capability="echo", correlation_id="c")

    assert repository.events[-1][1]["code"] == "CAPABILITY_DEPENDENCY_DISABLED"


@pytest.mark.asyncio
async def test_transitive_dependency_is_validated():
    governance, repository = service(
        capability_registry(
            definition("test.root", connector_capability="root", enabled=False),
            definition("test.mid", connector_capability="mid", dependencies=("test.root",)),
            definition("test.echo", dependencies=("test.mid",)),
        )
    )

    with pytest.raises(CAPABILITY_DEPENDENCY_DISABLED):
        await governance.authorize_execution(Actor("creator-1", "creator"), connector_id="echo", connector_capability="echo", correlation_id="c")

    assert repository.events[-1][1]["code"] == "CAPABILITY_DEPENDENCY_DISABLED"


@pytest.mark.asyncio
async def test_dependency_cycle_is_detected():
    governance, repository = service(
        capability_registry(
            definition("test.a", connector_capability="a", dependencies=("test.b",)),
            definition("test.b", connector_capability="b", dependencies=("test.a",)),
        )
    )

    with pytest.raises(CAPABILITY_DEPENDENCY_CYCLE):
        await governance.authorize_execution(Actor("creator-1", "creator"), connector_id="echo", connector_capability="a", correlation_id="c")

    assert repository.events[-1][1]["code"] == "CAPABILITY_DEPENDENCY_CYCLE"


@pytest.mark.asyncio
async def test_permission_denied_blocks_before_connector():
    governance, repository = service(capability_registry(definition("test.echo")))

    with pytest.raises(CAPABILITY_PERMISSION_DENIED):
        await governance.authorize_execution(Actor("agent-1", "agent"), connector_id="echo", connector_capability="echo", correlation_id="c")

    assert repository.events[-1][1]["code"] == "CAPABILITY_PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_connector_unavailable_blocks_execution():
    governance, repository = service(capability_registry(definition("test.echo")), connector_registry(False))

    with pytest.raises(CONNECTOR_UNAVAILABLE):
        await governance.authorize_execution(Actor("creator-1", "creator"), connector_id="echo", connector_capability="echo", correlation_id="c")

    assert repository.events[-1][1]["code"] == "CONNECTOR_UNAVAILABLE"


@pytest.mark.asyncio
async def test_authorized_execution_is_audited():
    governance, repository = service(capability_registry(definition("test.echo")))

    authorization = await governance.authorize_execution(Actor("creator-1", "creator"), connector_id="echo", connector_capability="echo", correlation_id="c")

    assert authorization.capability.capability_id == "test.echo"
    assert repository.events[-1][0] == "capability.execution.authorized"
    assert repository.events[-1][1]["authorized"] is True
