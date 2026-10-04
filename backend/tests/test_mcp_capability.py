from __future__ import annotations

import json

import httpx
import pytest

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.mcp import (
    McpToolCertification,
    McpToolProvider,
    discover_mcp_adapters,
    parse_mcp_servers,
)
from app.capabilities.policy import CapabilityDenied


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, arguments))
        return {"content": [{"type": "text", "text": "ok"}], "isError": False}


def _authorization(*capabilities: str, external_effects_allowed: bool = False) -> MissionAuthorization:
    return MissionAuthorization(
        allowed_capabilities=list(capabilities),
        external_effects_allowed=external_effects_allowed,
        authorized_by="creator",
        authorized_at="2026-10-03T00:00:00Z",
    )


def _certification(
    *,
    capability: str = "research.code_search",
    read_only: bool = True,
    production_enabled: bool = True,
) -> McpToolCertification:
    return McpToolCertification(
        capability=capability,
        actions=frozenset({"search"}),
        read_only=read_only,
        idempotent=read_only,
        destructive=False,
        origin="mcp:github",
        license="provider-terms",
        security_review="approved",
        shadow_enabled=True,
        production_enabled=production_enabled,
    )


@pytest.mark.asyncio
async def test_mcp_provider_is_hidden_behind_logical_capability() -> None:
    client = FakeMcpClient()
    provider = McpToolProvider(
        server="github",
        tool="search_code",
        client=client,
        certification=_certification(),
    )
    from app.capabilities.providers import RoutedCapabilityAdapter

    adapter = RoutedCapabilityAdapter(capability="research.code_search", providers=[provider])
    gateway = CapabilityGateway()
    gateway.register(adapter)

    assert adapter.name == "research.code_search"
    assert "github" not in adapter.name
    assert adapter.external_effect is False

    result = await gateway.execute(
        CapabilityIntent(
            capability="research.code_search",
            action="search",
            arguments={"query": "OpportunityLease"},
        ),
        CapabilityContext(
            mission_id="mission-1",
            authorization=_authorization("research.code_search"),
        ),
    )

    assert result.ok is True
    assert result.data["provider"] == "mcp:github:search_code"
    assert client.calls == [("search_code", {"query": "OpportunityLease"})]


@pytest.mark.asyncio
async def test_provider_specific_name_never_becomes_authority() -> None:
    client = FakeMcpClient()
    provider = McpToolProvider(
        server="github",
        tool="search_code",
        client=client,
        certification=_certification(),
    )
    from app.capabilities.providers import RoutedCapabilityAdapter

    gateway = CapabilityGateway()
    gateway.register(RoutedCapabilityAdapter(capability="research.code_search", providers=[provider]))

    with pytest.raises(CapabilityDenied):
        await gateway.execute(
            CapabilityIntent(
                capability="mcp.github.search_code",
                action="search",
                arguments={"query": "x"},
            ),
            CapabilityContext(
                mission_id="mission-1",
                authorization=_authorization("research.code_search"),
            ),
        )
    assert client.calls == []


def test_mcp_config_requires_local_mapping_and_certification_metadata() -> None:
    with pytest.raises(ValueError, match="origin, license and security_review"):
        parse_mcp_servers(json.dumps([{
            "name": "github",
            "endpoint": "https://example.com/mcp",
            "tools": {
                "search_code": {
                    "capability": "research.code_search",
                    "actions": ["search"],
                    "read_only": True,
                }
            },
        }]))


def test_mcp_config_rejects_duplicate_servers() -> None:
    with pytest.raises(ValueError, match="duplicate MCP server"):
        parse_mcp_servers(
            '[{"name":"github","endpoint":"https://one.example/mcp"},'
            '{"name":"github","endpoint":"https://two.example/mcp"}]'
        )


def test_mcp_config_rejects_read_only_destructive_overlap() -> None:
    with pytest.raises(ValueError, match="read-only and destructive"):
        parse_mcp_servers(json.dumps([{
            "name": "github",
            "endpoint": "https://example.com/mcp",
            "tools": {
                "danger": {
                    "capability": "repo.write",
                    "actions": ["write"],
                    "read_only": True,
                    "destructive": True,
                    "origin": "mcp:github",
                    "license": "provider-terms",
                    "security_review": "approved",
                }
            },
        }]))


@pytest.mark.asyncio
async def test_remote_annotations_do_not_lower_risk_without_local_certification() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        requests.append(payload)
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "x", "version": "1"}},
            })
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "tools": [{
                        "name": "write_file",
                        "annotations": {"readOnlyHint": True, "idempotentHint": True},
                    }]
                },
            })
        raise AssertionError(method)

    raw = json.dumps([{
        "name": "github",
        "endpoint": "https://example.com/mcp",
        "tools": {
            "write_file": {
                "capability": "repo.write",
                "actions": ["write"],
                "origin": "mcp:github",
                "license": "provider-terms",
                "security_review": "approved",
                "production_enabled": True,
            }
        },
    }])
    adapters = await discover_mcp_adapters(raw, transport=httpx.MockTransport(handler))
    assert len(adapters) == 1
    adapter = adapters[0]
    assert adapter.name == "repo.write"
    assert adapter.external_effect is True

    gateway = CapabilityGateway()
    gateway.register(adapter)
    with pytest.raises(CapabilityDenied, match="external effects"):
        await gateway.execute(
            CapabilityIntent(
                capability="repo.write",
                action="write",
                arguments={"path": "x"},
                idempotency_key="write-1",
            ),
            CapabilityContext(
                mission_id="mission-1",
                authorization=_authorization("repo.write"),
            ),
        )


@pytest.mark.asyncio
async def test_discovery_registers_only_locally_mapped_tools() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "x", "version": "1"}},
            })
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"tools": [{"name": "search_code"}, {"name": "delete_repo"}]},
            })
        raise AssertionError(method)

    raw = json.dumps([{
        "name": "github",
        "endpoint": "https://example.com/mcp",
        "tools": {
            "search_code": {
                "capability": "research.code_search",
                "actions": ["search"],
                "read_only": True,
                "origin": "mcp:github",
                "license": "provider-terms",
                "security_review": "approved",
                "shadow_enabled": True,
            }
        },
    }])
    adapters = await discover_mcp_adapters(raw, transport=httpx.MockTransport(handler))
    assert [adapter.name for adapter in adapters] == ["research.code_search"]
