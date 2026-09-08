from __future__ import annotations

from datetime import datetime, timezone

from app.capabilities.contracts import CapabilityIntent, MissionAuthorization


class CapabilityDenied(PermissionError):
    pass


def authorize_capability(intent: CapabilityIntent, authorization: MissionAuthorization) -> None:
    if authorization.expires_at is not None:
        expires_at = datetime.fromisoformat(authorization.expires_at.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise CapabilityDenied("mission authorization has expired")

    if intent.capability in authorization.denied_capabilities:
        raise CapabilityDenied(f"capability denied: {intent.capability}")
    if intent.capability not in authorization.allowed_capabilities:
        raise CapabilityDenied(f"capability not authorized: {intent.capability}")

    allowed_actions = authorization.scope.get("actions", {})
    if isinstance(allowed_actions, dict) and intent.capability in allowed_actions:
        actions = allowed_actions[intent.capability]
        if isinstance(actions, list) and intent.action not in actions:
            raise CapabilityDenied(f"action not authorized: {intent.action}")

    allowed_resources = authorization.scope.get("resources")
    if intent.resource is not None and isinstance(allowed_resources, list) and intent.resource not in allowed_resources:
        raise CapabilityDenied(f"resource not authorized: {intent.resource}")

    if intent.external_effect and not authorization.external_effects_allowed:
        raise CapabilityDenied("external effects are not authorized")
    if intent.idempotency_class.value == "AT_MOST_ONCE" and not intent.idempotency_key:
        raise CapabilityDenied("AT_MOST_ONCE capability requires idempotency_key")
