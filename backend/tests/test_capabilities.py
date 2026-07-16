from __future__ import annotations

import pytest

from app.automation.contracts import ConnectorCapability, ConnectorRequest, ConnectorResult, ConnectorStatus
from app.automation.registry import ConnectorRegistry
from app.capabilities.contracts import CAPABILITY_FRAMEWORK_VERSION, CapabilityDefinition, CapabilityPermission
from app.capabilities.registry import CapabilityError, CapabilityRegistry, default_capability_registry
from app.core.domain import Actor
from app.models.automation import AutomationExecution
from app.services.automation import AutomationService


class EchoConnector:
    connector_id = "echo"

    def capabilities(self) -> list[ConnectorCapability]:
        return [ConnectorCapability(name="echo", description="Echo payload", input_schema={})]

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"payload": request.payload})


class FakeAutomationRepository:
    async def execution(self, creator_id: str, connector_id: str, idempotency_key: str) -> AutomationExecution | None:
        return None

    async def add(self, item: AutomationExecution) -> AutomationExecution:
        item.id = "execution-1"
        return item

    async def add_event(self, aggregate_id: str, actor_id: str, actor_role: str, correlation_id: str, payload: dict) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def capability(
    capability_id: str,
    *,
    connector_id: str = "echo",
    connector_capability: str = "echo",
    enabled: bool = True,
    dependencies: tuple[str, ...] = (),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        name=capability_id,
        description=f"{capability_id} description",
        version="1.0.0",
        connector_id=connector_id,
        connector_capability=connector_capability,
        enabled=enabled,
        permissions=(CapabilityPermission.READ,),
        dependencies=dependencies,
    )


def test_default_capability_registry_discovers_github_first_and_with_versions():
    items = default_capability_registry().discover()

    assert items[0].capability_id.startswith("github.")
    assert items[0].version == "1.0.0"
    assert all(item.version.count(".") == 2 for item in items)
    assert "github.issues.create" in {item.capability_id for item in items}
    assert "rest.restricted.request" in {item.capability_id for item in items}


def test_capability_registry_rejects_invalid_metadata_and_duplicate_connector_mapping():
    registry = CapabilityRegistry()
    registry.register(capability("test.echo"))

    with pytest.raises(CapabilityError, match="already mapped"):
        registry.register(capability("test.echo.alias"))
    with pytest.raises(CapabilityError, match="version"):
        registry.register(CapabilityDefinition("bad.version", "Bad", "Bad", "v1", "x", "y", True, (CapabilityPermission.READ,)))


def test_capability_registry_validates_enabled_dependencies():
    registry = CapabilityRegistry()
    registry.register(capability("test.base", connector_capability="base", enabled=False))
    registry.register(capability("test.child", connector_capability="child", dependencies=("test.base",)))

    with pytest.raises(CapabilityError, match="dependency is disabled"):
        registry.validate_execution("echo", "child")


def test_capability_registry_returns_framework_version_on_success():
    registry = CapabilityRegistry()
    registry.register(capability("test.echo"))

    validation = registry.validate_execution("echo", "echo")

    assert validation.framework_version == CAPABILITY_FRAMEWORK_VERSION
    assert validation.capability.capability_id == "test.echo"


def test_capability_registry_supports_enable_disable():
    registry = CapabilityRegistry()
    registry.register(capability("test.echo"))

    registry.disable("test.echo")
    with pytest.raises(CapabilityError, match="disabled"):
        registry.validate_execution("echo", "echo")

    registry.enable("test.echo")
    assert registry.validate_execution("echo", "echo").capability.enabled is True


@pytest.mark.asyncio
async def test_automation_service_blocks_unregistered_connector_capability_before_execution():
    connector_registry = ConnectorRegistry()
    connector_registry.register(EchoConnector())
    capability_registry = CapabilityRegistry()
    service = AutomationService(FakeAutomationRepository(), connector_registry, capability_registry)  # type: ignore[arg-type]

    with pytest.raises(CapabilityError, match="not registered"):
        await service.execute(
            Actor(id="creator-1", role="creator"),
            connector_id="echo",
            capability="echo",
            payload={"message": "hello"},
            timeout_seconds=1,
            idempotency_key="same-key",
            correlation_id="correlation-1",
        )
