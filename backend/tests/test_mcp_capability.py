from __future__ import annotations

import pytest

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway
from app.capabilities.mcp import McpToolAdapter, McpToolDescriptor
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


@pytest.mark.asyncio
async def test_mcp_read_tool_is_a_granular_low_risk_capability() -> None:
    client = FakeMcpClient()
    descriptor = McpToolDescriptor(
        server="github",
        tool="search_code",
        read_only=True,
    )
    adapter = McpToolAdapter(client=client, descriptor=descriptor)
    gateway = CapabilityGateway()
    gateway.register(adapter)

    assert adapter.name == "mcp.github.search_code"
    assert adapter.external_effect is False

    result = await gateway.execute(
        CapabilityIntent(
            capability=adapter.name,
            action="call",
            arguments={"query": "OpportunityLease"},
        ),
        CapabilityContext(
            mission_id="mission-1",
            authorization=_authorization(adapter.name),
        ),
    )

    assert result.ok is True
    assert client.calls == [("search_code", {"query": "OpportunityLease"})]


@pytest.mark.asyncio
async def test_mcp_tool_never_runs_when_mission_does_not_authorize_its_exact_capability() -> None:
    client = FakeMcpClient()
    adapter = McpToolAdapter(
        client=client,
        descriptor=McpToolDescriptor(server="github", tool="create_pull_request", read_only=False),
    )
    gateway = CapabilityGateway()
    gateway.register(adapter)

    with pytest.raises(CapabilityDenied):
        await gateway.execute(
            CapabilityIntent(
                capability=adapter.name,
                action="call",
                arguments={"title": "unauthorized"},
                idempotency_key="attempt-1",
            ),
            CapabilityContext(
                mission_id="mission-1",
                authorization=_authorization("mcp.github.search_code", external_effects_allowed=True),
            ),
        )

    assert client.calls == []


def test_mcp_config_rejects_duplicate_servers() -> None:
    from app.capabilities.mcp import parse_mcp_servers

    with pytest.raises(ValueError, match="duplicate MCP server"):
        parse_mcp_servers(
            '[{"name":"github","endpoint":"https://one.example/mcp"},'
            '{"name":"github","endpoint":"https://two.example/mcp"}]'
        )


@pytest.mark.asyncio
async def test_untrusted_mcp_write_tool_defaults_to_at_most_once_and_external_effect() -> None:
    client = FakeMcpClient()
    adapter = McpToolAdapter(
        client=client,
        descriptor=McpToolDescriptor(server="github", tool="write_file"),
    )
    gateway = CapabilityGateway()
    gateway.register(adapter)

    assert adapter.external_effect is True

    with pytest.raises(CapabilityDenied, match="external effects"):
        await gateway.execute(
            CapabilityIntent(
                capability=adapter.name,
                action="call",
                arguments={"path": "x"},
                idempotency_key="write-1",
            ),
            CapabilityContext(
                mission_id="mission-1",
                authorization=_authorization(adapter.name),
            ),
        )
    assert client.calls == []


def test_mcp_server_tool_certification_is_explicit() -> None:
    from app.capabilities.mcp import parse_mcp_servers

    [server] = parse_mcp_servers(
        '[{"name":"github","endpoint":"https://example.com/mcp",'
        '"read_only_tools":["search_code"],"idempotent_tools":["update_issue"]}]'
    )
    assert server.read_only_tools == frozenset({"search_code"})
    assert server.idempotent_tools == frozenset({"update_issue"})
    assert "create_pull_request" not in server.read_only_tools
