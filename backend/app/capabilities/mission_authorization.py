from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.domain import Actor, MissionStatus, require_creator
from app.models.entities import Mission
from app.repositories.domain import DomainRepository
from app.services.domain import NotFoundError


async def set_mission_authorization(
    repository: DomainRepository,
    *,
    actor: Actor,
    mission_id: str,
    authorization: dict[str, Any],
    correlation_id: str,
) -> Mission:
    require_creator(actor, "set Mission authorization scope")
    mission = await repository.get_for_update(Mission, mission_id)
    if mission is None or mission.creator_id != actor.id:
        raise NotFoundError("Mission not found")
    if mission.status != MissionStatus.AUTHORIZED.value:
        raise ValueError("Mission authorization scope can only be set while Mission is AUTHORIZED")

    previous_version = int((mission.authorization_json or {}).get("version", 0))
    requested_version = int(authorization.get("version", 1))
    if requested_version <= previous_version:
        raise ValueError("Mission authorization version must increase")

    mission.authorization_json = {
        "allowed_capabilities": list(authorization.get("allowed_capabilities", [])),
        "denied_capabilities": list(authorization.get("denied_capabilities", [])),
        "scope": dict(authorization.get("scope", {})),
        "external_effects_allowed": bool(authorization.get("external_effects_allowed", False)),
        "risk_level": str(authorization.get("risk_level", "low")),
        "budget": dict(authorization.get("budget", {})),
        "expires_at": authorization.get("expires_at"),
        "version": requested_version,
        "authorized_by": actor.id,
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
    }
    await repository.add_event(
        "mission_authorization_scoped",
        "mission",
        mission.id,
        actor.id,
        actor.role,
        correlation_id,
        {
            "version": requested_version,
            "allowed_capabilities": mission.authorization_json["allowed_capabilities"],
            "denied_capabilities": mission.authorization_json["denied_capabilities"],
            "external_effects_allowed": mission.authorization_json["external_effects_allowed"],
            "risk_level": mission.authorization_json["risk_level"],
        },
    )
    await repository.commit()
    return mission
