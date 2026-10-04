"""MCP discovery and provider mapping for logical Creation OS capabilities.

Remote MCP metadata is discovery input only. A tool becomes executable only when the local
MCP_SERVERS_JSON configuration maps it to a logical capability and supplies the provider
certification metadata used by the central router.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, CapabilityResult, IdempotencyClass
from app.capabilities.providers import (
    CapabilityProviderMetadata,
    ProviderUnavailable,
    RoutedCapabilityAdapter,
)

_SAFE_NAME = re.compile(r"[^a-z0-9_.-]+")
DEFAULT_PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    """The configured MCP server could not satisfy a protocol request."""


class McpClient(Protocol):
    async def call_tool(self, tool: str, arguments: dict) -> dict: ...


@dataclass(frozen=True)
class McpToolCertification:
    capability: str
    actions: frozenset[str]
    read_only: bool
    idempotent: bool
    destructive: bool
    origin: str
    license: str
    security_review: str
    shadow_enabled: bool = False
    production_enabled: bool = False
    health: str = "healthy"
    cost: float = 0.0
    latency_ms: float = 0.0
    success_rate: float = 1.0


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    endpoint: str
    tools: dict[str, McpToolCertification]
    token_env: str | None = None
    protocol_version: str = DEFAULT_PROTOCOL_VERSION


def _normalize_name(value: str) -> str:
    return _SAFE_NAME.sub("_", value.strip().lower()).strip("._-")


def _strings(value: object, *, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be a non-empty list of strings")
    return frozenset(item.strip() for item in value)


def _tool_certification(server: str, tool: str, raw: object) -> McpToolCertification:
    if not isinstance(raw, dict):
        raise ValueError(f"MCP tool certification must be an object: {server}.{tool}")
    capability = _normalize_name(str(raw.get("capability", "")))
    if not capability:
        raise ValueError(f"MCP tool certification requires capability: {server}.{tool}")
    actions = _strings(raw.get("actions"), field=f"{server}.{tool}.actions")
    read_only = bool(raw.get("read_only", False))
    idempotent = bool(raw.get("idempotent", False))
    destructive = bool(raw.get("destructive", False))
    if read_only and destructive:
        raise ValueError(f"MCP tool cannot be read-only and destructive: {server}.{tool}")

    origin = str(raw.get("origin", "")).strip()
    license_name = str(raw.get("license", "")).strip()
    security_review = str(raw.get("security_review", "")).strip()
    if not origin or not license_name or not security_review:
        raise ValueError(f"MCP tool certification requires origin, license and security_review: {server}.{tool}")

    return McpToolCertification(
        capability=capability,
        actions=actions,
        read_only=read_only,
        idempotent=idempotent,
        destructive=destructive,
        origin=origin,
        license=license_name,
        security_review=security_review,
        shadow_enabled=bool(raw.get("shadow_enabled", False)),
        production_enabled=bool(raw.get("production_enabled", False)),
        health=str(raw.get("health", "healthy")),
        cost=float(raw.get("cost", 0.0)),
        latency_ms=float(raw.get("latency_ms", 0.0)),
        success_rate=float(raw.get("success_rate", 1.0)),
    )


class RemoteMcpClient:
    """Small Streamable-HTTP MCP client with JSON and SSE response support."""

    def __init__(
        self,
        *,
        endpoint: str,
        bearer_token: str | None = None,
        timeout_seconds: float = 15.0,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        endpoint = endpoint.strip()
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("MCP endpoint must be absolute HTTP(S)")
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.protocol_version = protocol_version
        self.transport = transport
        self._session_id: str | None = None
        self._initialized = False
        self._request_id = 0

    def _headers(self) -> dict[str, str]:
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
            "mcp-protocol-version": self.protocol_version,
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        if self.bearer_token:
            headers["authorization"] = f"Bearer {self.bearer_token}"
        return headers

    async def _post(self, payload: dict, *, expect_response: bool = True) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = await client.post(self.endpoint, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            raise McpError(f"MCP HTTP {response.status_code}")
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        if not expect_response or response.status_code == 202 or not response.content:
            return {}

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            data_lines = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
            if not data_lines:
                raise McpError("MCP SSE response contained no data event")
            try:
                body = json.loads(data_lines[-1])
            except json.JSONDecodeError as exc:
                raise McpError("MCP SSE response was not valid JSON") from exc
        else:
            try:
                body = response.json()
            except ValueError as exc:
                raise McpError("MCP response was not valid JSON") from exc

        if not isinstance(body, dict):
            raise McpError("MCP response must be an object")
        if body.get("error"):
            error = body["error"]
            detail = error.get("message") if isinstance(error, dict) else "remote error"
            raise McpError(f"MCP remote error: {detail}")
        result = body.get("result", {})
        if not isinstance(result, dict):
            raise McpError("MCP result must be an object")
        return result

    async def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._request_id += 1
        return await self._post({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            **({"params": params} if params is not None else {}),
        })

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "the-creation-os", "version": "0.1.0"},
            },
        )
        negotiated = result.get("protocolVersion")
        if isinstance(negotiated, str) and negotiated:
            self.protocol_version = negotiated
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_response=False)
        self._initialized = True

    async def list_tools(self) -> set[str]:
        await self.ensure_initialized()
        tools: set[str] = set()
        cursor: str | None = None
        while True:
            result = await self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            raw_tools = result.get("tools", [])
            if not isinstance(raw_tools, list):
                raise McpError("MCP tools/list returned malformed tools")
            for raw in raw_tools:
                if isinstance(raw, dict) and isinstance(raw.get("name"), str):
                    tools.add(raw["name"])
            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return tools

    async def call_tool(self, tool: str, arguments: dict) -> dict:
        await self.ensure_initialized()
        return await self._rpc("tools/call", {"name": tool, "arguments": arguments})


class McpToolProvider:
    """A locally certified MCP tool implementing one logical capability."""

    def __init__(
        self,
        *,
        server: str,
        tool: str,
        client: McpClient,
        certification: McpToolCertification,
    ) -> None:
        self.provider_name = f"mcp:{_normalize_name(server)}:{_normalize_name(tool)}"
        self.capability = certification.capability
        self.actions = certification.actions
        self.external_effect = not certification.read_only
        if certification.read_only:
            self.minimum_idempotency_class = IdempotencyClass.SAFE
        elif certification.idempotent and not certification.destructive:
            self.minimum_idempotency_class = IdempotencyClass.IDEMPOTENT
        else:
            self.minimum_idempotency_class = IdempotencyClass.AT_MOST_ONCE
        self._tool = tool
        self._client = client
        self.metadata = CapabilityProviderMetadata(
            origin=certification.origin,
            license=certification.license,
            security_review=certification.security_review,
            health=certification.health,
            cost=certification.cost,
            latency_ms=certification.latency_ms,
            success_rate=certification.success_rate,
            shadow_enabled=certification.shadow_enabled,
            production_enabled=certification.production_enabled,
        )

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        if intent.action not in self.actions:
            raise ProviderUnavailable(f"{self.provider_name} does not support {intent.action}")
        try:
            data = await self._client.call_tool(self._tool, dict(intent.arguments))
        except (McpError, httpx.HTTPError, TimeoutError) as exc:
            raise ProviderUnavailable(f"{self.provider_name} unavailable: {exc.__class__.__name__}") from exc
        if not isinstance(data, dict):
            raise ProviderUnavailable(f"{self.provider_name} returned malformed data")
        if bool(data.get("isError", False)):
            return CapabilityResult(
                capability=self.capability,
                action=intent.action,
                ok=False,
                error={"code": "MCP_TOOL_ERROR", "detail": "remote tool reported an error"},
            )
        return CapabilityResult(
            capability=self.capability,
            action=intent.action,
            ok=True,
            data={"result": data},
        )


def parse_mcp_servers(raw: str) -> list[McpServerConfig]:
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MCP_SERVERS_JSON must be valid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("MCP_SERVERS_JSON must contain a JSON array")

    servers: list[McpServerConfig] = []
    names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each MCP server config must be an object")
        name = _normalize_name(str(item.get("name", "")))
        endpoint = str(item.get("endpoint", "")).strip()
        if not name or not endpoint:
            raise ValueError("each MCP server requires name and endpoint")
        if name in names:
            raise ValueError(f"duplicate MCP server name: {name}")
        names.add(name)

        raw_tools = item.get("tools", {})
        if not isinstance(raw_tools, dict):
            raise ValueError(f"MCP server tools must be an object: {name}")
        tools = {
            str(tool): _tool_certification(name, str(tool), certification)
            for tool, certification in raw_tools.items()
        }
        servers.append(McpServerConfig(
            name=name,
            endpoint=endpoint,
            token_env=str(item.get("token_env", "")).strip() or None,
            protocol_version=str(item.get("protocol_version", DEFAULT_PROTOCOL_VERSION)),
            tools=tools,
        ))
    return servers


async def discover_mcp_adapters(
    raw_config: str,
    *,
    timeout_seconds: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[RoutedCapabilityAdapter]:
    grouped: dict[str, list[McpToolProvider]] = {}
    for server in parse_mcp_servers(raw_config):
        token = os.environ.get(server.token_env) if server.token_env else None
        if server.token_env and not token:
            raise ValueError(f"MCP credential environment variable is missing: {server.token_env}")
        client = RemoteMcpClient(
            endpoint=server.endpoint,
            bearer_token=token,
            timeout_seconds=timeout_seconds,
            protocol_version=server.protocol_version,
            transport=transport,
        )
        discovered = await client.list_tools()

        # Discovery alone grants nothing. Only a locally mapped/certified tool is registered.
        for tool, certification in server.tools.items():
            if tool not in discovered:
                raise ValueError(f"certified MCP tool was not discovered: {server.name}.{tool}")
            provider = McpToolProvider(
                server=server.name,
                tool=tool,
                client=client,
                certification=certification,
            )
            grouped.setdefault(provider.capability, []).append(provider)

    return [
        RoutedCapabilityAdapter(capability=capability, providers=providers)
        for capability, providers in sorted(grouped.items())
    ]
