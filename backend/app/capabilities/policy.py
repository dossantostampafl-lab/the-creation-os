from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.capabilities.contracts import CapabilityIntent, IdempotencyClass, MissionAuthorization

# Weakest to strongest. An Agent may ask for a stronger guarantee than the adapter requires,
# never a weaker one.
_IDEMPOTENCY_ORDER = {
    IdempotencyClass.SAFE: 0,
    IdempotencyClass.IDEMPOTENT: 1,
    IdempotencyClass.AT_MOST_ONCE: 2,
}


class CapabilityDenied(PermissionError):
    pass


@dataclass(frozen=True)
class CapabilityDeclaration:
    """What the adapter itself says about what running it does.

    The Agent's `CapabilityIntent` arrives from the model, so nothing in it can be trusted to
    describe consequences: a model that writes `external_effect: false` must not thereby turn a
    capability that reaches the outside world into one that does not. The adapter declares that,
    and an adapter that declares nothing is treated as the most dangerous case.
    """

    external_effect: bool = True
    minimum_idempotency_class: IdempotencyClass = IdempotencyClass.AT_MOST_ONCE


def declaration_for(adapter: object) -> CapabilityDeclaration:
    return CapabilityDeclaration(
        external_effect=bool(getattr(adapter, "external_effect", True)),
        minimum_idempotency_class=getattr(
            adapter, "minimum_idempotency_class", IdempotencyClass.AT_MOST_ONCE,
        ),
    )


def effective_idempotency_class(
    intent: CapabilityIntent, declaration: CapabilityDeclaration,
) -> IdempotencyClass:
    requested = _IDEMPOTENCY_ORDER[intent.idempotency_class]
    required = _IDEMPOTENCY_ORDER[declaration.minimum_idempotency_class]
    return intent.idempotency_class if requested >= required else declaration.minimum_idempotency_class


def _check_scope(intent: CapabilityIntent, authorization: MissionAuthorization) -> None:
    """The Creator's narrowing. A scope entry that cannot be read is a restriction, never none."""
    allowed_actions = authorization.scope.get("actions")
    if allowed_actions is not None:
        if not isinstance(allowed_actions, dict):
            raise CapabilityDenied("mission scope 'actions' could not be read")
        if intent.capability in allowed_actions:
            actions = allowed_actions[intent.capability]
            if isinstance(actions, str):
                actions = [actions]
            if not isinstance(actions, list):
                raise CapabilityDenied(f"mission scope for {intent.capability} could not be read")
            if intent.action not in actions:
                raise CapabilityDenied(f"action not authorized: {intent.action}")

    allowed_resources = authorization.scope.get("resources")
    if allowed_resources is not None:
        if isinstance(allowed_resources, str):
            allowed_resources = [allowed_resources]
        if not isinstance(allowed_resources, list):
            raise CapabilityDenied("mission scope 'resources' could not be read")
        if intent.resource is None:
            raise CapabilityDenied("resource required: this Mission is narrowed to named resources")
        if intent.resource not in allowed_resources:
            raise CapabilityDenied(f"resource not authorized: {intent.resource}")


def authorize_capability(
    intent: CapabilityIntent,
    authorization: MissionAuthorization,
    declaration: CapabilityDeclaration | None = None,
) -> None:
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

    _check_scope(intent, authorization)

    declared = declaration or CapabilityDeclaration()
    # The adapter's word on consequences, raised by the Agent's if the Agent asks for more.
    external_effect = declared.external_effect or intent.external_effect
    if external_effect and not authorization.external_effects_allowed:
        raise CapabilityDenied("external effects are not authorized")
    if effective_idempotency_class(intent, declared) is IdempotencyClass.AT_MOST_ONCE and not intent.idempotency_key:
        raise CapabilityDenied("AT_MOST_ONCE capability requires idempotency_key")
