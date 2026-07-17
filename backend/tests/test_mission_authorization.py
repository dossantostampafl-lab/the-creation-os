from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.domain import Actor
from app.models.entities import Mission
from app.models.mission_authorization import MissionAuthorization
from app.services.mission_authorization import (
    CREATOR_AUTHORITY_REQUIRED,
    MISSION_AUTHORIZATION_EXPIRED,
    MISSION_AUTHORIZATION_REQUIRED,
    MISSION_AUTHORIZATION_REVOKED,
    MISSION_AUTHORIZATION_SUSPENDED,
    MISSION_CAPABILITY_NOT_ALLOWED,
    MISSION_PROJECT_MISMATCH,
    MISSION_RESOURCE_NOT_ALLOWED,
    MISSION_SCOPE_VIOLATION,
    MissionActionContext,
    MissionAuthorizationService,
)


class FakeMissionAuthorizationRepository:
    def __init__(self) -> None:
        self.mission_id = str(uuid.uuid4())
        self.mission_row = Mission(id=self.mission_id, inception_id=str(uuid.uuid4()), creator_id="creator-1", title="Demo", objective="Finish demo", status="drafted")
        self.items: list[MissionAuthorization] = []
        self.events: list[tuple[str, dict]] = []
        self.commits = 0

    async def mission(self, mission_id: str, *, lock: bool = False):
        return self.mission_row if mission_id == self.mission_id else None

    async def active_for_mission(self, mission_id: str, *, lock: bool = False):
        return next((item for item in self.items if item.mission_id == mission_id and item.status in {"pending", "authorized", "suspended"}), None)

    async def latest_for_mission(self, mission_id: str):
        return next((item for item in reversed(self.items) if item.mission_id == mission_id), None)

    async def add(self, item: MissionAuthorization):
        item.id = item.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        item.created_at = item.created_at or now
        item.updated_at = item.updated_at or now
        self.items.append(item)
        return item

    async def add_event(self, event_type, aggregate_id, actor_id, actor_role, correlation_id, payload):
        self.events.append((event_type, payload))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def actor(role: str = "creator") -> Actor:
    return Actor("creator-1", role)


async def authorized_service() -> tuple[MissionAuthorizationService, FakeMissionAuthorizationRepository, MissionAuthorization]:
    repo = FakeMissionAuthorizationRepository()
    service = MissionAuthorizationService(repo)  # type: ignore[arg-type]
    item = await service.request_authorization(
        actor(),
        repo.mission_id,
        project_id="local",
        scope={"actions": ["read_project_files", "run_tests"]},
        allowed_capabilities=["rest.restricted.request"],
        allowed_resources=["project/*"],
        restrictions={},
        expires_at=None,
        metadata={},
        correlation_id="c",
    )
    await service.approve(actor(), repo.mission_id, "c")
    return service, repo, item


@pytest.mark.asyncio
async def test_creator_can_request_and_approve_authorization():
    repo = FakeMissionAuthorizationRepository()
    service = MissionAuthorizationService(repo)  # type: ignore[arg-type]

    pending = await service.request_authorization(
        actor(),
        repo.mission_id,
        project_id="local",
        scope={"actions": ["read_project_files", "run_tests"]},
        allowed_capabilities=["rest.restricted.request"],
        allowed_resources=["project/*"],
        restrictions={},
        expires_at=None,
        metadata={},
        correlation_id="c",
    )
    approved = await service.approve(actor(), repo.mission_id, "c")

    assert pending.id == approved.id
    assert approved.status == "authorized"
    assert [event[0] for event in repo.events] == ["mission.authorization.requested", "mission.authorization.approved"]


@pytest.mark.asyncio
async def test_non_creator_cannot_approve():
    repo = FakeMissionAuthorizationRepository()
    service = MissionAuthorizationService(repo)  # type: ignore[arg-type]
    await service.request_authorization(actor(), repo.mission_id, project_id="local", scope={"actions": ["read_project_files"]}, allowed_capabilities=["*"], allowed_resources=["*"], restrictions={}, expires_at=None, metadata={}, correlation_id="c")

    with pytest.raises(CREATOR_AUTHORITY_REQUIRED):
        await service.approve(actor("agent"), repo.mission_id, "c")


@pytest.mark.asyncio
async def test_missing_or_pending_authorization_blocks_execution():
    repo = FakeMissionAuthorizationRepository()
    service = MissionAuthorizationService(repo)  # type: ignore[arg-type]
    context = MissionActionContext(repo.mission_id, "local", "read_project_files", "rest.restricted.request", "project/file")

    with pytest.raises(MISSION_AUTHORIZATION_REQUIRED):
        await service.check_action(actor(), context, "c")

    await service.request_authorization(actor(), repo.mission_id, project_id="local", scope={"actions": ["read_project_files"]}, allowed_capabilities=["rest.restricted.request"], allowed_resources=["project/*"], restrictions={}, expires_at=None, metadata={}, correlation_id="c")
    with pytest.raises(Exception, match="pending"):
        await service.check_action(actor(), context, "c")


@pytest.mark.asyncio
async def test_authorized_action_inside_scope_passes_and_audits():
    service, repo, _ = await authorized_service()

    item = await service.check_action(actor(), MissionActionContext(repo.mission_id, "local", "read_project_files", "rest.restricted.request", "project/file"), "c")

    assert item.status == "authorized"
    assert repo.events[-1][0] == "mission.action.authorized"


@pytest.mark.asyncio
async def test_scope_capability_resource_and_project_violations_are_blocked():
    service, repo, _ = await authorized_service()

    with pytest.raises(MISSION_SCOPE_VIOLATION):
        await service.check_action(actor(), MissionActionContext(repo.mission_id, "local", "git_push", "rest.restricted.request", "project/file"), "c")
    with pytest.raises(MISSION_CAPABILITY_NOT_ALLOWED):
        await service.check_action(actor(), MissionActionContext(repo.mission_id, "local", "read_project_files", "github.issues.create", "project/file"), "c")
    with pytest.raises(MISSION_RESOURCE_NOT_ALLOWED):
        await service.check_action(actor(), MissionActionContext(repo.mission_id, "local", "read_project_files", "rest.restricted.request", "other/file"), "c")
    with pytest.raises(MISSION_PROJECT_MISMATCH):
        await service.check_action(actor(), MissionActionContext(repo.mission_id, "other", "read_project_files", "rest.restricted.request", "project/file"), "c")
    assert "mission.scope.exceeded" in [event[0] for event in repo.events]


@pytest.mark.asyncio
async def test_suspended_revoked_and_expired_authorizations_block():
    service, repo, item = await authorized_service()
    context = MissionActionContext(repo.mission_id, "local", "read_project_files", "rest.restricted.request", "project/file")

    await service.suspend(actor(), repo.mission_id, "c")
    with pytest.raises(MISSION_AUTHORIZATION_SUSPENDED):
        await service.check_action(actor(), context, "c")

    item.status = "authorized"
    item.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(MISSION_AUTHORIZATION_EXPIRED):
        await service.check_action(actor(), context, "c")

    item.expires_at = None
    await service.revoke(actor(), repo.mission_id, "c")
    with pytest.raises(MISSION_AUTHORIZATION_REVOKED):
        await service.check_action(actor(), context, "c")


@pytest.mark.asyncio
async def test_complete_changes_state_without_deleting_history():
    service, repo, item = await authorized_service()

    completed = await service.complete(actor(), repo.mission_id, "c")

    assert completed.status == "completed"
    assert item in repo.items
    assert repo.events[-1][0] == "mission.authorization.completed"
