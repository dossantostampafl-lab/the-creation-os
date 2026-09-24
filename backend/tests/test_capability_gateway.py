from __future__ import annotations

import pytest

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.policy import CapabilityDenied


class EchoAdapter:
    name = "echo"

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(
            capability=intent.capability,
            action=intent.action,
            ok=True,
            data={"arguments": intent.arguments},
        )


def context(**overrides) -> CapabilityContext:
    """A Mission and what it is allowed to do, as the runtime hands it to the gateway."""
    return CapabilityContext(mission_id="mission-a", authorization=authorization(**overrides))


def authorization(**overrides) -> MissionAuthorization:
    payload = {
        "allowed_capabilities": ["echo"],
        "denied_capabilities": [],
        "scope": {},
        "external_effects_allowed": False,
        "risk_level": "low",
        "budget": {},
        "version": 1,
        "authorized_by": "creator",
        "authorized_at": "2026-09-08T00:00:00Z",
    }
    payload.update(overrides)
    return MissionAuthorization(**payload)


@pytest.mark.asyncio
async def test_gateway_executes_only_explicitly_allowed_capability() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    result = await gateway.execute(
        CapabilityIntent(capability="echo", action="say", arguments={"value": "ok"}),
        context(),
    )
    assert result.ok is True
    assert result.data["arguments"] == {"value": "ok"}


@pytest.mark.asyncio
async def test_deny_wins_over_allow() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    with pytest.raises(CapabilityDenied, match="denied"):
        await gateway.execute(
            CapabilityIntent(capability="echo", action="say"),
            context(denied_capabilities=["echo"]),
        )


@pytest.mark.asyncio
async def test_external_effect_requires_explicit_authorization() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    with pytest.raises(CapabilityDenied, match="external effects"):
        await gateway.execute(
            CapabilityIntent(capability="echo", action="send", external_effect=True),
            context(),
        )


@pytest.mark.asyncio
async def test_at_most_once_requires_idempotency_key() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    with pytest.raises(CapabilityDenied, match="idempotency_key"):
        await gateway.execute(
            CapabilityIntent(
                capability="echo",
                action="send",
                idempotency_class=IdempotencyClass.AT_MOST_ONCE,
            ),
            context(),
        )


@pytest.mark.asyncio
async def test_scope_restricts_action_and_resource() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    scoped = context(scope={"actions": {"echo": ["say"]}, "resources": ["project:alpha"]})
    with pytest.raises(CapabilityDenied, match="action not authorized"):
        await gateway.execute(CapabilityIntent(capability="echo", action="delete"), scoped)
    with pytest.raises(CapabilityDenied, match="resource not authorized"):
        await gateway.execute(
            CapabilityIntent(capability="echo", action="say", resource="project:beta"),
            scoped,
        )


@pytest.mark.asyncio
async def test_expired_authorization_is_denied() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    with pytest.raises(CapabilityDenied, match="expired"):
        await gateway.execute(
            CapabilityIntent(capability="echo", action="say"),
            context(expires_at="2020-01-01T00:00:00Z"),
        )
