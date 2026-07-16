from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.automation.contracts import ConnectorCapability, ConnectorRejected, ConnectorRequest, ConnectorResult, ConnectorStatus

CLOUD_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}
SAFE_HEADERS = {"accept", "content-type", "user-agent", "x-request-id", "x-correlation-id"}
SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization", "x-api-key"}


class RestrictedRestConnector:
    connector_id = "restricted_rest"

    def __init__(
        self,
        *,
        allowed_hosts: set[str],
        allowed_methods: set[str],
        max_response_bytes: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}
        self.allowed_methods = {method.upper() for method in allowed_methods}
        self.max_response_bytes = max_response_bytes
        self._client = client

    def capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(
                name="http_request",
                description="Restricted outbound HTTP request to pre-authorized public hosts.",
                input_schema={
                    "type": "object",
                    "required": ["method", "url"],
                    "properties": {
                        "method": {"type": "string", "enum": sorted(self.allowed_methods)},
                        "url": {"type": "string"},
                        "headers": {"type": "object"},
                        "json": {"type": "object"},
                    },
                },
            )
        ]

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.capability != "http_request":
            raise ConnectorRejected("Restricted REST connector only supports http_request")
        method = str(request.payload.get("method", "")).upper()
        url = str(request.payload.get("url", ""))
        headers = self._safe_headers(request.payload.get("headers", {}))
        body = request.payload.get("json")
        host = await self._validate_target(method, url)
        timeout = httpx.Timeout(request.timeout_seconds)

        client = self._client or httpx.AsyncClient(follow_redirects=False, timeout=timeout)
        close_client = self._client is None
        try:
            response = await client.request(method, url, headers=headers, json=body)
            content = response.content[: self.max_response_bytes]
            truncated = len(response.content) > self.max_response_bytes
            return ConnectorResult(
                status=ConnectorStatus.SUCCEEDED,
                output={
                    "host": host,
                    "method": method,
                    "url": self._redacted_url(url),
                    "status_code": response.status_code,
                    "headers": self._safe_response_headers(dict(response.headers)),
                    "body_preview": content.decode(response.encoding or "utf-8", errors="replace"),
                    "truncated": truncated,
                },
            )
        except httpx.TimeoutException as exc:
            return ConnectorResult(status=ConnectorStatus.TIMEOUT, error_code="rest_timeout", error_message=exc.__class__.__name__)
        except httpx.HTTPError as exc:
            return ConnectorResult(status=ConnectorStatus.FAILED, error_code="rest_http_error", error_message=exc.__class__.__name__)
        finally:
            if close_client:
                await client.aclose()

    async def _validate_target(self, method: str, url: str) -> str:
        if method not in self.allowed_methods:
            raise ConnectorRejected("REST method is not allowed")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ConnectorRejected("REST URL scheme is not allowed")
        host = (parsed.hostname or "").lower()
        if host not in self.allowed_hosts:
            raise ConnectorRejected("REST host is not pre-authorized")
        await self._reject_private_host(host)
        return host

    async def _reject_private_host(self, host: str) -> None:
        try:
            literal = ipaddress.ip_address(host)
            self._reject_private_ip(literal)
            return
        except ValueError:
            pass
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
        for info in infos:
            self._reject_private_ip(ipaddress.ip_address(info[4][0]))

    def _reject_private_ip(self, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address in CLOUD_METADATA_IPS
        ):
            raise ConnectorRejected("REST target resolves to a blocked network")

    def _safe_headers(self, headers: object) -> dict[str, str]:
        if not isinstance(headers, dict):
            raise ConnectorRejected("REST headers must be an object")
        safe: dict[str, str] = {}
        for key, value in headers.items():
            normalized = str(key).lower()
            if normalized in SENSITIVE_HEADERS:
                raise ConnectorRejected("REST request header is not allowed")
            if normalized not in SAFE_HEADERS:
                raise ConnectorRejected("REST request header is not in the safe allowlist")
            safe[str(key)] = str(value)
        return safe

    def _safe_response_headers(self, headers: dict[str, str]) -> dict[str, str]:
        return {key: value for key, value in headers.items() if key.lower() in SAFE_HEADERS}

    def _redacted_url(self, url: str) -> str:
        parsed = urlparse(url)
        port = f":{parsed.port}" if parsed.port else ""
        path = parsed.path or "/"
        return f"{parsed.scheme}://{parsed.hostname}{port}{path}"
