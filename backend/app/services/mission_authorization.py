from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.core.domain import Actor, AuthorizationDenied, DomainError, require_creator
from app.models.mission_authorization import MissionAuthorization
from app.repositories.mission_authorization import MissionAuthorizationRepository

DEFAULT_ALLOWED_ACTIONS = {
    "read_project_files",
    "modify_project_files",
    "run_tests",
    "run_lint",
    "run_typecheck",
    "build_containers",
    "start_containers",
    "inspect_logs",
    "update_documentation",
    "create_local_commit",
}
SENSITIVE_ACTIONS = {
    "git_push",
    "create_pull_request",
    "deploy",
    "production_change",
    "delete_project",
    "access_other_project",
    "use_real_financial_account",
}


class MissionAuthorizationStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    COMPLETED = "completed"


class MissionAuthorizationError(DomainError):
    pass


class MISSION_AUTHORIZATION_REQUIRED(MissionAuthorizationError):
    pass


class MISSION_NOT_AUTHORIZED(MissionAuthorizationError):
    pass


class MISSION_AUTHORIZATION_SUSPENDED(MissionAuthorizationError):
    pass


class MISSION_AUTHORIZATION_REVOKED(MissionAuthorizationError):
    pass


class MISSION_AUTHORIZATION_EXPIRED(MissionAuthorizationError):
    pass


class MISSION_SCOPE_VIOLATION(MissionAuthorizationError):
    pass


class MISSION_CAPABILITY_NOT_ALLOWED(MissionAuthorizationError):
    pass


class MISSION_RESOURCE_NOT_ALLOWED(MissionAuthorizationError):
    pass


class MISSION_PROJECT_MISMATCH(MissionAuthorizationError):
    pass


class CREATOR_AUTHORITY_REQUIRED(MissionAuthorizationError):
    pass


@dataclass(frozen=True)
class MissionActionContext:
    mission_id: str
    project_id: str
    action: str
    capability_id: str
    resource: str | None = None
    reason: str | None = None


class MissionAuthorizationService:
    def __init__(self, repository: MissionAuthorizationRepository) -> None:
        self.repository = repository

    async def request_authorization(
        self,
        actor: Actor,
        mission_id: str,
        *,
        project_id: str,
        scope: dict[str, Any],
        allowed_capabilities: list[str],
        allowed_resources: list[str],
        restrictions: dict[str, Any] | None,
        expires_at: datetime | None,
        metadata: dict[str, Any] | None,
        correlation_id: str,
    ) -> MissionAuthorization:
        require_creator(actor, "request mission authorization")
        mission = await self.repository.mission(mission_id)
        if mission is None:
            raise MISSION_AUTHORIZATION_REQUIRED("Mission does not exist")
        existing = await self.repository.active_for_mission(mission_id)
        if existing is not None:
            return existing
        item = await self.repository.add(
            MissionAuthorization(
                mission_id=mission_id,
                project_id=project_id,
                creator_id=actor.id,
                status=MissionAuthorizationStatus.PENDING.value,
                scope_json=self._normalize_scope(scope),
                allowed_capabilities_json=sorted(set(allowed_capabilities)),
                allowed_resources_json=sorted(set(allowed_resources)),
                restrictions_json=restrictions or {"sensitive_actions_denied": sorted(SENSITIVE_ACTIONS)},
                expires_at=expires_at,
                metadata_json=metadata or {},
            )
        )
        await self.repository.add_event("mission.authorization.requested", item.id, actor.id, actor.role, correlation_id, {"mission_id": mission_id, "project_id": project_id})
        await self.repository.commit()
        return item

    async def approve(self, actor: Actor, mission_id: str, correlation_id: str) -> MissionAuthorization:
        self._require_creator_authority(actor)
        item = await self._active_or_required(mission_id, lock=True)
        if item.status != MissionAuthorizationStatus.PENDING.value:
            raise MISSION_NOT_AUTHORIZED("Mission authorization is not pending")
        item.status = MissionAuthorizationStatus.AUTHORIZED.value
        item.approved_at = datetime.now(timezone.utc)
        await self.repository.add_event("mission.authorization.approved", item.id, actor.id, actor.role, correlation_id, {"mission_id": mission_id})
        await self.repository.commit()
        return item

    async def suspend(self, actor: Actor, mission_id: str, correlation_id: str) -> MissionAuthorization:
        self._require_creator_authority(actor)
        item = await self._active_or_required(mission_id, lock=True)
        item.status = MissionAuthorizationStatus.SUSPENDED.value
        item.suspended_at = datetime.now(timezone.utc)
        await self.repository.add_event("mission.authorization.suspended", item.id, actor.id, actor.role, correlation_id, {"mission_id": mission_id})
        await self.repository.commit()
        return item

    async def revoke(self, actor: Actor, mission_id: str, correlation_id: str) -> MissionAuthorization:
        self._require_creator_authority(actor)
        item = await self._active_or_required(mission_id, lock=True)
        item.status = MissionAuthorizationStatus.REVOKED.value
        item.revoked_at = datetime.now(timezone.utc)
        await self.repository.add_event("mission.authorization.revoked", item.id, actor.id, actor.role, correlation_id, {"mission_id": mission_id})
        await self.repository.commit()
        return item

    async def complete(self, actor: Actor, mission_id: str, correlation_id: str) -> MissionAuthorization:
        require_creator(actor, "complete mission authorization")
        item = await self._active_or_required(mission_id, lock=True)
        item.status = MissionAuthorizationStatus.COMPLETED.value
        item.completed_at = datetime.now(timezone.utc)
        await self.repository.add_event("mission.authorization.completed", item.id, actor.id, actor.role, correlation_id, {"mission_id": mission_id})
        await self.repository.commit()
        return item

    async def get(self, actor: Actor, mission_id: str) -> MissionAuthorization | None:
        require_creator(actor, "view mission authorization")
        return await self.repository.latest_for_mission(mission_id)

    async def check_action(self, actor: Actor, context: MissionActionContext, correlation_id: str) -> MissionAuthorization:
        item = await self._active_or_required(context.mission_id)
        try:
            self._validate_state(item)
            if item.project_id != context.project_id:
                raise MISSION_PROJECT_MISMATCH("Mission authorization belongs to another project")
            actions = set(item.scope_json.get("actions") or [])
            if context.action in SENSITIVE_ACTIONS or context.action not in actions:
                raise MISSION_SCOPE_VIOLATION(f"Action is outside mission scope: {context.action}")
            allowed_capabilities = set(item.allowed_capabilities_json or [])
            if "*" not in allowed_capabilities and context.capability_id not in allowed_capabilities:
                raise MISSION_CAPABILITY_NOT_ALLOWED(f"Capability is outside mission scope: {context.capability_id}")
            if not self._resource_allowed(context.resource, list(item.allowed_resources_json or [])):
                raise MISSION_RESOURCE_NOT_ALLOWED(f"Resource is outside mission scope: {context.resource}")
            await self.repository.add_event(
                "mission.action.authorized",
                item.id,
                actor.id,
                actor.role,
                correlation_id,
                {"mission_id": context.mission_id, "action": context.action, "capability_id": context.capability_id, "resource": context.resource},
            )
            await self.repository.commit()
            return item
        except MissionAuthorizationError as exc:
            await self.repository.add_event(
                "mission.action.denied",
                item.id,
                actor.id,
                actor.role,
                correlation_id,
                {"mission_id": context.mission_id, "action": context.action, "capability_id": context.capability_id, "resource": context.resource, "code": exc.__class__.__name__, "reason": context.reason},
            )
            if isinstance(exc, (MISSION_SCOPE_VIOLATION, MISSION_CAPABILITY_NOT_ALLOWED, MISSION_RESOURCE_NOT_ALLOWED)):
                await self.repository.add_event(
                    "mission.scope.exceeded",
                    item.id,
                    actor.id,
                    actor.role,
                    correlation_id,
                    {"mission_id": context.mission_id, "action": context.action, "reason": str(exc)},
                )
            await self.repository.commit()
            raise

    def _validate_state(self, item: MissionAuthorization) -> None:
        if item.status == MissionAuthorizationStatus.PENDING.value:
            raise MISSION_NOT_AUTHORIZED("Mission is pending Creator authorization")
        if item.status == MissionAuthorizationStatus.SUSPENDED.value:
            raise MISSION_AUTHORIZATION_SUSPENDED("Mission authorization is suspended")
        if item.status == MissionAuthorizationStatus.REVOKED.value:
            raise MISSION_AUTHORIZATION_REVOKED("Mission authorization is revoked")
        if item.expires_at is not None and self._aware(item.expires_at) <= datetime.now(timezone.utc):
            raise MISSION_AUTHORIZATION_EXPIRED("Mission authorization is expired")
        if item.status != MissionAuthorizationStatus.AUTHORIZED.value:
            raise MISSION_NOT_AUTHORIZED("Mission is not authorized")

    async def _active_or_required(self, mission_id: str, *, lock: bool = False) -> MissionAuthorization:
        item = await self.repository.active_for_mission(mission_id, lock=lock)
        if item is None:
            latest = await self.repository.latest_for_mission(mission_id)
            if latest is not None and latest.status == MissionAuthorizationStatus.REVOKED.value:
                raise MISSION_AUTHORIZATION_REVOKED("Mission authorization is revoked")
            if latest is not None and latest.status == MissionAuthorizationStatus.COMPLETED.value:
                raise MISSION_NOT_AUTHORIZED("Mission authorization is completed")
            raise MISSION_AUTHORIZATION_REQUIRED("Mission authorization is required")
        return item

    def _require_creator_authority(self, actor: Actor) -> None:
        try:
            require_creator(actor, "change mission authorization")
        except AuthorizationDenied as exc:
            raise CREATOR_AUTHORITY_REQUIRED("Only Creator may change mission authorization") from exc

    def _normalize_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        actions = set(scope.get("actions") or [])
        denied = actions & SENSITIVE_ACTIONS
        if denied:
            raise MISSION_SCOPE_VIOLATION(f"Sensitive actions cannot be in default scope: {sorted(denied)}")
        valid = actions & DEFAULT_ALLOWED_ACTIONS
        return {"actions": sorted(valid), "version": str(scope.get("version") or "1.0")}

    def _resource_allowed(self, resource: str | None, allowed: list[str]) -> bool:
        if not resource:
            return True
        if "*" in allowed:
            return True
        for entry in allowed:
            if resource == entry:
                return True
            if entry.endswith("/*") and resource.startswith(entry[:-1]):
                return True
        return False

    def _aware(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
