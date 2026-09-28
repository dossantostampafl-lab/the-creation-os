from __future__ import annotations

import httpx
import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, MissionAuthorization
from app.capabilities.web_providers import (
    MCPWebProvider,
    NoWebProvider,
    ProviderUnavailable,
    RemoteContractWebProvider,
    WebProviderMetadata,
    select_web_provider,
)


def _context() -> CapabilityContext:
    return CapabilityContext(
        mission_id="mission-remote-provider",
        authorization=MissionAuthorization(
            allowed_capabilities=["web"],
            authorized_by="creator",
            authorized_at="2026-09-27T00:00:00Z",
        ),
    )


def _metadata(*actions: str, review: str = "approved", shadow: bool = True, production: bool = False) -> WebProviderMetadata:
    return WebProviderMetadata(
        origin="remote:test",
        license="provider-terms",
        security_review=review,
        supported_actions=frozenset(actions),
        shadow_enabled=shadow,
        production_enabled=production,
    )


@pytest.mark.asyncio
async def test_remote_provider_normalizes_success_and_classifies_rate_limit_and_malformed_json() -> None:
    def success(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json={"items": [{"url": "https://example.com"}]})

    provider = RemoteContractWebProvider(
        name="remote",
        endpoint="https://provider.example/execute",
        api_key="secret",
        actions=("search",),
        transport=httpx.MockTransport(success),
        metadata=_metadata("search"),
    )
    data = await provider.execute(
        CapabilityIntent(capability="web", action="search", resource="creation os"),
        _context(),
    )
    assert data["items"][0]["url"] == "https://example.com"

    limited = RemoteContractWebProvider(
        name="limited",
        endpoint="https://provider.example/execute",
        actions=("search",),
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={"error": "rate"})),
        metadata=_metadata("search"),
    )
    with pytest.raises(ProviderUnavailable, match="429"):
        await limited.execute(CapabilityIntent(capability="web", action="search", resource="q"), _context())

    malformed = RemoteContractWebProvider(
        name="malformed",
        endpoint="https://provider.example/execute",
        actions=("search",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json")),
        metadata=_metadata("search"),
    )
    with pytest.raises(ProviderUnavailable, match="malformed JSON"):
        await malformed.execute(CapabilityIntent(capability="web", action="search", resource="q"), _context())


def test_uncertified_or_incomplete_provider_cannot_be_selected_for_material_use() -> None:
    pending = RemoteContractWebProvider(
        name="pending",
        endpoint="https://provider.example/execute",
        actions=("search",),
        metadata=_metadata("search", review="pending", shadow=True, production=True),
    )
    assert select_web_provider("search", [pending]).name == "pending"
    with pytest.raises(NoWebProvider):
        select_web_provider("search", [pending], material=True)

    incomplete = RemoteContractWebProvider(
        name="incomplete",
        endpoint="https://provider.example/execute",
        actions=("search",),
        metadata=WebProviderMetadata(
            origin="",
            license="",
            security_review="approved",
            supported_actions=frozenset({"search"}),
            shadow_enabled=True,
            production_enabled=True,
        ),
    )
    with pytest.raises(NoWebProvider):
        select_web_provider("search", [incomplete])


@pytest.mark.asyncio
async def test_mcp_provider_requires_configured_transport_and_preserves_contract() -> None:
    metadata = WebProviderMetadata(
        origin="mcp:playwright",
        license="provider-terms",
        security_review="approved",
        supported_actions=frozenset({"crawl"}),
        shadow_enabled=True,
        production_enabled=False,
    )
    missing = MCPWebProvider(
        name="playwright-mcp",
        tool_name="observe",
        actions=("crawl",),
        caller=None,
        metadata=metadata,
    )
    with pytest.raises(ProviderUnavailable, match="not configured"):
        await missing.execute(CapabilityIntent(capability="web", action="crawl", resource="https://example.com"), _context())

    calls: list[tuple[str, dict]] = []

    async def caller(tool_name: str, payload: dict) -> dict:
        calls.append((tool_name, payload))
        return {"url": payload["resource"], "content": "observed"}

    configured = MCPWebProvider(
        name="playwright-mcp",
        tool_name="observe",
        actions=("crawl",),
        caller=caller,
        metadata=metadata,
    )
    result = await configured.execute(
        CapabilityIntent(capability="web", action="crawl", resource="https://example.com"),
        _context(),
    )
    assert result["content"] == "observed"
    assert calls[0][0] == "observe"
    assert calls[0][1]["mission_id"] == "mission-remote-provider"
