from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.automation import capability_service as automation_capability_service
from app.auth.dependencies import get_sovereign_creator
from app.capabilities.registry import CapabilityError, default_capability_registry
from app.core.domain import Actor, AuthorizationDenied
from app.main import app
from app.models.capability_registry import RegisteredCapability
from app.schemas.auth import TokenPayload
from app.services.capabilities import CapabilityPersistenceService


class FakeCapabilityRepository:
    def __init__(self) -> None:
        self.items: dict[str, RegisteredCapability] = {}
        self.events: list[dict] = []
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

    async def add_event(self, aggregate_id: str, actor_id: str, actor_role: str, correlation_id: str, payload: dict) -> None:
        self.events.append(payload)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def service_with_fake_repo(repository: FakeCapabilityRepository) -> CapabilityPersistenceService:
    return CapabilityPersistenceService(repository, default_capability_registry())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_capability_sync_persists_registered_definitions():
    repository = FakeCapabilityRepository()
    service = service_with_fake_repo(repository)

    items = await service.sync()

    assert "github.repositories.list" in {item.capability_id for item in items}
    assert repository.items["github.repositories.list"].mandatory is True
    assert repository.items["github.issues.create"].dependencies_json == ["github.repositories.list"]
    assert len(repository.items["github.issues.create"].capability_fingerprint) == 64


@pytest.mark.asyncio
async def test_capability_enable_disable_are_creator_only_and_audited():
    repository = FakeCapabilityRepository()
    service = service_with_fake_repo(repository)
    actor = Actor(id="creator-1", role="creator")
    await service.sync()

    disabled = await service.disable(actor, "github.issues.create", "correlation-1")
    assert disabled.enabled is False
    enabled = await service.enable(actor, "github.issues.create", "correlation-2")

    assert enabled.enabled is True
    assert repository.events == [
        {"capability_id": "github.issues.create", "enabled": False, "mandatory": False},
        {"capability_id": "github.issues.create", "enabled": True, "mandatory": False},
    ]
    with pytest.raises(AuthorizationDenied):
        await service.disable(Actor(id="agent-1", role="agent"), "github.issues.create", "correlation-3")


@pytest.mark.asyncio
async def test_mandatory_capability_cannot_be_disabled():
    repository = FakeCapabilityRepository()
    service = service_with_fake_repo(repository)
    await service.sync()

    with pytest.raises(CapabilityError, match="Mandatory Capability cannot be disabled"):
        await service.disable(Actor(id="creator-1", role="creator"), "github.repositories.list", "correlation-1")


@pytest.mark.asyncio
async def test_synced_registry_reflects_persisted_disabled_state():
    repository = FakeCapabilityRepository()
    service = service_with_fake_repo(repository)
    await service.sync()
    await service.disable(Actor(id="creator-1", role="creator"), "github.issues.create", "correlation-1")

    registry = await service.synced_registry()

    with pytest.raises(CapabilityError, match="disabled"):
        registry.validate_execution("github", "create_issue")


@pytest.mark.asyncio
async def test_capability_api_lists_and_changes_state_without_real_database():
    repository = FakeCapabilityRepository()
    service = service_with_fake_repo(repository)
    app.dependency_overrides[get_sovereign_creator] = lambda: TokenPayload(
        sub="creator-1",
        type="access",
        jti=str(uuid.uuid4()),
        exp=9999999999,
    )
    app.dependency_overrides[automation_capability_service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            listed = await client.get("/api/v1/automation/capabilities")
            disabled = await client.post("/api/v1/automation/capabilities/github.issues.create/disable")
            blocked = await client.post("/api/v1/automation/capabilities/github.repositories.list/disable")
    finally:
        app.dependency_overrides.clear()

    assert listed.status_code == 200
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert blocked.status_code == 409
