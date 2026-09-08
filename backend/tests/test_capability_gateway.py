from __future__ import annotations

import pytest

from app.capabilities.contracts import (
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.policy import CapabilityDenied


class EchoAdapter:
    name = "echo"

    async def execute(self, intent: CapabilityIntent) -> CapabilityResult:
        return CapabilityResult(
            capability=intent.capability,
            action=intent.action,
            ok=True,
            data={"arguments": intent.arguments},
        )


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
        authorization(),
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
            authorization(denied_capabilities=["echo"]),
        )


@pytest.mark.asyncio
async def test_external_effect_requires_explicit_authorization() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    with pytest.raises(CapabilityDenied, match="external effects"):
        await gateway.execute(
            CapabilityIntent(capability="echo", action="send", external_effect=True),
            authorization(),
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
            authorization(),
        )
