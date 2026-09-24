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
    external_effect = False
    minimum_idempotency_class = IdempotencyClass.SAFE

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


class ReachesOutsideAdapter:
    """An adapter that does something out in the world and says so."""

    name = "outside"
    external_effect = True
    minimum_idempotency_class = IdempotencyClass.AT_MOST_ONCE

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(capability=intent.capability, action=intent.action, ok=True)


class UndeclaredAdapter:
    name = "undeclared"

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(capability=intent.capability, action=intent.action, ok=True)


@pytest.mark.asyncio
async def test_the_model_cannot_talk_an_external_effect_away() -> None:
    """The adapter says what running it does; the request is not evidence about consequences."""
    gateway = CapabilityGateway()
    gateway.register(ReachesOutsideAdapter())

    with pytest.raises(CapabilityDenied, match="external effects"):
        await gateway.execute(
            CapabilityIntent(capability="outside", action="send", external_effect=False),
            context(allowed_capabilities=["outside"]),
        )


@pytest.mark.asyncio
async def test_the_model_cannot_talk_an_idempotency_requirement_away() -> None:
    gateway = CapabilityGateway()
    gateway.register(ReachesOutsideAdapter())
    allowed = context(allowed_capabilities=["outside"], external_effects_allowed=True)

    with pytest.raises(CapabilityDenied, match="idempotency_key"):
        await gateway.execute(
            CapabilityIntent(
                capability="outside", action="send", idempotency_class=IdempotencyClass.SAFE,
            ),
            allowed,
        )

    accepted = await gateway.execute(
        CapabilityIntent(
            capability="outside", action="send",
            idempotency_class=IdempotencyClass.SAFE, idempotency_key="once-only",
        ),
        allowed,
    )
    assert accepted.ok


@pytest.mark.asyncio
async def test_an_adapter_that_declares_nothing_is_treated_as_the_worst_case() -> None:
    gateway = CapabilityGateway()
    gateway.register(UndeclaredAdapter())

    with pytest.raises(CapabilityDenied, match="external effects"):
        await gateway.execute(
            CapabilityIntent(capability="undeclared", action="do"),
            context(allowed_capabilities=["undeclared"]),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [
    {"actions": {"echo": "say"}},          # a single action written without the list
    {"actions": "say"},                    # not a mapping at all
    {"actions": {"echo": {"say": True}}},  # a shape nobody can read as a list
])
async def test_a_scope_written_the_wrong_way_narrows_rather_than_opens(scope: dict) -> None:
    """Fail closed: a Creator's restriction that cannot be read must never mean 'no restriction'."""
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    scoped = context(scope=scope)

    if scope == {"actions": {"echo": "say"}}:
        # The one readable shorthand is honoured, and still restricts.
        assert (await gateway.execute(CapabilityIntent(capability="echo", action="say"), scoped)).ok
        with pytest.raises(CapabilityDenied):
            await gateway.execute(CapabilityIntent(capability="echo", action="delete"), scoped)
        return

    with pytest.raises(CapabilityDenied, match="could not be read"):
        await gateway.execute(CapabilityIntent(capability="echo", action="say"), scoped)


@pytest.mark.asyncio
async def test_a_mission_narrowed_to_resources_refuses_a_request_without_one() -> None:
    gateway = CapabilityGateway()
    gateway.register(EchoAdapter())
    scoped = context(scope={"resources": ["project:alpha"]})

    with pytest.raises(CapabilityDenied, match="resource required"):
        await gateway.execute(CapabilityIntent(capability="echo", action="say"), scoped)
