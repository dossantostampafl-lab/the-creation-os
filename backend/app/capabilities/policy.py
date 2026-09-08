from __future__ import annotations

from app.capabilities.contracts import CapabilityIntent, MissionAuthorization


class CapabilityDenied(PermissionError):
    pass


def authorize_capability(intent: CapabilityIntent, authorization: MissionAuthorization) -> None:
    if intent.capability in authorization.denied_capabilities:
        raise CapabilityDenied(f"capability denied: {intent.capability}")
    if intent.capability not in authorization.allowed_capabilities:
        raise CapabilityDenied(f"capability not authorized: {intent.capability}")
    if intent.external_effect and not authorization.external_effects_allowed:
        raise CapabilityDenied("external effects are not authorized")
    if intent.idempotency_class.value == "AT_MOST_ONCE" and not intent.idempotency_key:
        raise CapabilityDenied("AT_MOST_ONCE capability requires idempotency_key")
