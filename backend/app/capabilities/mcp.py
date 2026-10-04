"""MCP tools exposed as ordinary Creation OS capabilities.

A Universe never receives an MCP client or credential. Remote MCP servers are discovered by
the worker and every tool becomes its own capability (mcp.<server>.<tool>). Mission
Authorization therefore remains the only source of authority.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
)

_SAFE_NAME = re.compile(r"[^a-z0-9_.-]+")
DEFAULT_PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    """The configured MCP server could not satisfy a protocol request."""


class McpClient(Protocol):
    async def call_tool(self, tool: str, arguments: dict) -> dict: ...


@dataclass(frozen=True)
class McpToolDescriptor:
    server: str
    tool: str
    read_only: bool = False
    idempotent: bool = False
    destructive: bool = False

    @property
    def capability(self) -> str:
        server = _normalize_name(self.server)
        tool = _normalize_name(self.tool)
        if not server or not tool:
            raise ValueError("MCP server and tool names must contain a usable character")
        return f"mcp.{server}.{tool}"


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    endpoint: str
    token_env: str | None = None
    protocol_version: str = DEFAULT_PROTOCOL_VERSION
    read_only_tools: frozenset[str] = frozenset()
    idempotent_tools: frozenset[str] = frozenset()
    destructive_tools: frozenset[str] = frozenset()


def _normalize_name(value: str) -> str:
    return _SAFE_NAME.sub("_", value.strip().lower()).strip("._-")


def _tool_names(value: object, *, field: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be a list of non-empty tool names")
    return frozenset(item.strip() for item in value)


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
            data_lines = [
                line[5:].strip()
                for line in response.text.splitlines()
                if line.startswith("data:")
            ]
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
        await self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_response=False,
        )
        self._initialized = True

    async def list_tools(self) -> list[McpToolDescriptor]:
        await self.ensure_initialized()
        server = _normalize_name(httpx.URL(self.endpoint).host or "server")
        descriptors: list[McpToolDescriptor] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = await self._rpc("tools/list", params)
            raw_tools = result.get("tools", [])
            if not isinstance(raw_tools, list):
                raise McpError("MCP tools/list returned malformed tools")
            for raw in raw_tools:
                if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
                    continue
                annotations = raw.get("annotations") if isinstance(raw.get("annotations"), dict) else {}
                descriptors.append(McpToolDescriptor(
                    server=server,
                    tool=raw["name"],
                    read_only=bool(annotations.get("readOnlyHint", False)),
                    idempotent=bool(annotations.get("idempotentHint", False)),
                    destructive=bool(annotations.get("destructiveHint", False)),
                ))
            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return descriptors

    async def call_tool(self, tool: str, arguments: dict) -> dict:
        await self.ensure_initialized()
        return await self._rpc("tools/call", {"name": tool, "arguments": arguments})


class McpToolAdapter:
    """One remote MCP tool mapped to one exact CapabilityGateway capability."""

    def __init__(self, *, client: McpClient, descriptor: McpToolDescriptor) -> None:
        self.client = client
        self.descriptor = descriptor
        self.name = descriptor.capability
        self.external_effect = not descriptor.read_only
        if descriptor.read_only:
            self.minimum_idempotency_class = IdempotencyClass.SAFE
        elif descriptor.idempotent and not descriptor.destructive:
            self.minimum_idempotency_class = IdempotencyClass.IDEMPOTENT
        else:
            self.minimum_idempotency_class = IdempotencyClass.AT_MOST_ONCE

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        if intent.action != "call":
            return CapabilityResult(
                capability=self.name,
                action=intent.action,
                ok=False,
                error={"code": "MCP_ACTION_REJECTED", "detail": "MCP tools support only action=call"},
            )
        try:
            data = await self.client.call_tool(self.descriptor.tool, dict(intent.arguments))
        except (McpError, httpx.HTTPError, TimeoutError) as exc:
            return CapabilityResult(
                capability=self.name,
                action=intent.action,
                ok=False,
                error={"code": "MCP_REQUEST_FAILED", "detail": exc.__class__.__name__},
            )
        is_error = bool(data.get("isError", False)) if isinstance(data, dict) else True
        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=not is_error,
            data=data if isinstance(data, dict) and not is_error else {},
            error=(
                {"code": "MCP_TOOL_ERROR", "detail": "remote tool reported an error"}
                if is_error else {}
            ),
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
        token_env = str(item.get("token_env", "")).strip() or None
        servers.append(McpServerConfig(
            name=name,
            endpoint=endpoint,
            token_env=token_env,
            protocol_version=str(item.get("protocol_version", DEFAULT_PROTOCOL_VERSION)),
            read_only_tools=_tool_names(item.get("read_only_tools"), field="read_only_tools"),
            idempotent_tools=_tool_names(item.get("idempotent_tools"), field="idempotent_tools"),
            destructive_tools=_tool_names(item.get("destructive_tools"), field="destructive_tools"),
        ))
    return servers


async def discover_mcp_adapters(
    raw_config: str,
    *,
    timeout_seconds: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[McpToolAdapter]:
    adapters: list[McpToolAdapter] = []
    seen: set[str] = set()
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
        for descriptor in discovered:
            # Remote annotations are discovery metadata, not authority. Risk can only be
            # lowered by local certification in MCP_SERVERS_JSON.
            named = McpToolDescriptor(
                server=server.name,
                tool=descriptor.tool,
                read_only=descriptor.tool in server.read_only_tools,
                idempotent=descriptor.tool in server.idempotent_tools,
                destructive=descriptor.tool in server.destructive_tools,
            )
            adapter = McpToolAdapter(client=client, descriptor=named)
            if adapter.name in seen:
                raise ValueError(f"duplicate MCP capability: {adapter.name}")
            seen.add(adapter.name)
            adapters.append(adapter)
    return adapters
