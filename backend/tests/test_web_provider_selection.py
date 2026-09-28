from __future__ import annotations

from typing import Any

import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, MissionAuthorization
from app.capabilities.web import WebCapabilityAdapter
from app.capabilities.web_providers import (
    CallableWebProvider,
    NoWebProvider,
    ProviderUnavailable,
    WebProviderMetadata,
    select_web_provider,
)


def _metadata(*actions: str, healthy: bool = True, production: bool = True) -> WebProviderMetadata:
    return WebProviderMetadata(
        origin="test",
        license="test",
        security_review="approved",
        supported_actions=frozenset(actions),
        shadow_enabled=True,
        production_enabled=production,
        health="healthy" if healthy else "unavailable",
    )


def _context(*, hosts: list[str] | None = None) -> CapabilityContext:
    scope: dict[str, Any] = {"actions": {"web": ["search", "crawl", "extract"]}}
    if hosts is not None:
        scope["web_allowed_hosts"] = hosts
    return CapabilityContext(
        mission_id="mission-provider",
        authorization=MissionAuthorization(
            allowed_capabilities=["web"],
            scope=scope,
            authorized_by="creator",
            authorized_at="2026-09-27T00:00:00Z",
        ),
    )


@pytest.mark.asyncio
async def test_provider_preference_and_fallback_are_deterministic() -> None:
    calls: list[str] = []

    async def unavailable(intent, context):
        calls.append("preferred")
        raise ProviderUnavailable("temporary")

    async def fallback(intent, context):
        calls.append("fallback")
        return {"items": [{"url": "https://example.com/result", "title": "result"}]}

    preferred = CallableWebProvider(
        name="preferred",
        actions=("search",),
        runner=unavailable,
        metadata=_metadata("search"),
    )
    second = CallableWebProvider(
        name="fallback",
        actions=("search",),
        runner=fallback,
        metadata=_metadata("search"),
    )

    async def resolve(_host: str) -> list[str]:
        return ["93.184.216.34"]

    adapter = WebCapabilityAdapter(
        providers=[second, preferred],
        preferred_providers=["preferred", "fallback"],
        resolve=resolve,
    )
    result = await adapter.execute(
        CapabilityIntent(capability="web", action="search", resource="creation os"),
        _context(),
    )

    assert result.ok
    assert result.data["provider"] == "fallback"
    assert calls == ["preferred", "fallback"]


def test_select_provider_respects_action_health_and_certification_for_material_use() -> None:
    async def runner(intent, context):
        return {}

    healthy = CallableWebProvider(
        name="healthy",
        actions=("crawl",),
        runner=runner,
        metadata=_metadata("crawl"),
    )
    unavailable = CallableWebProvider(
        name="down",
        actions=("crawl",),
        runner=runner,
        metadata=_metadata("crawl", healthy=False),
    )
    shadow_only = CallableWebProvider(
        name="shadow",
        actions=("crawl",),
        runner=runner,
        metadata=WebProviderMetadata(
            origin="test",
            license="test",
            security_review="pending",
            supported_actions=frozenset({"crawl"}),
            shadow_enabled=True,
            production_enabled=False,
        ),
    )

    assert select_web_provider("crawl", [unavailable, healthy]).name == "healthy"
    assert select_web_provider("crawl", [shadow_only]).name == "shadow"
    with pytest.raises(NoWebProvider):
        select_web_provider("crawl", [shadow_only], material=True)


@pytest.mark.asyncio
async def test_provider_result_cannot_escape_creator_host_scope() -> None:
    async def runner(intent, context):
        return {"items": [{"url": "https://outside.example/result"}]}

    provider = CallableWebProvider(
        name="scoped",
        actions=("search",),
        runner=runner,
        metadata=_metadata("search"),
    )

    async def resolve(_host: str) -> list[str]:
        return ["93.184.216.34"]

    adapter = WebCapabilityAdapter(providers=[provider], resolve=resolve)
    result = await adapter.execute(
        CapabilityIntent(capability="web", action="search", resource="query"),
        _context(hosts=["docs.example.com"]),
    )

    assert not result.ok
    assert result.error["code"] == "WEB_REJECTED"
    assert "authorized list" in result.error["detail"]


@pytest.mark.asyncio
async def test_no_provider_and_unsupported_action_fail_closed() -> None:
    adapter = WebCapabilityAdapter()
    no_provider = await adapter.execute(
        CapabilityIntent(capability="web", action="extract", resource="https://example.com"),
        _context(),
    )
    unsupported = await adapter.execute(
        CapabilityIntent(capability="web", action="delete", resource="https://example.com"),
        _context(),
    )
    assert not no_provider.ok and no_provider.error["code"] == "WEB_REJECTED"
    assert not unsupported.ok and unsupported.error["code"] == "WEB_REJECTED"
