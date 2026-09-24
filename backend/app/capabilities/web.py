"""Read a public page.

The Agent chooses the address, so this capability treats it as untrusted. Only http and
https are allowed, every hop of a redirect is checked again, and an address that resolves
to anything but the public internet is refused — the loopback interface, the private
ranges and the cloud metadata service all sit on the same network as this system's own
database, Redis and gateways, and are exactly what an attacker would aim a fetch at. The
address the connection actually reached is checked as well, so a name that answers with a
public address and then a private one does not get through.

Reading changes nothing out there, so this declares no external effect; it still runs only
when the Mission's authorization allows the capability, and the Creator can narrow it to a
list of hosts through the authorization scope.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
)

CAPABILITY = "web"
ACTION = "fetch"
MAX_REDIRECTS = 3

Resolver = Callable[[str], Awaitable[list[str]]]


class WebError(RuntimeError):
    """The Agent asked for something this capability will not fetch."""


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def _public_address(raw: str) -> None:
    """Refuse an address that is not on the public internet."""
    try:
        address = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError as exc:
        raise WebError("web address could not be read") from exc
    # is_global is false for loopback, private, link-local (cloud metadata) and reserved.
    if not address.is_global:
        raise WebError("web address is not on the public internet")


class WebCapabilityAdapter:
    name = CAPABILITY
    # Reading a page changes nothing out there, and reading it twice is the same as once.
    external_effect = False
    minimum_idempotency_class = IdempotencyClass.SAFE

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_bytes: int = 500_000,
        transport: httpx.AsyncBaseTransport | None = None,
        resolve: Resolver | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0:
            raise ValueError("web timeout and max_bytes must be positive")
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._transport = transport
        self._resolve = resolve or _resolve

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        if intent.action != ACTION:
            return self._refused(intent, f"web supports only the '{ACTION}' action")
        try:
            # One budget for the whole fetch, redirects included, so a page that dribbles
            # bytes out forever cannot hold a worker.
            async with asyncio.timeout(self._timeout_seconds):
                data = await self._fetch(intent, context)
        except WebError as exc:
            return self._refused(intent, str(exc))
        # A malformed URL reaches this as ValueError (urlsplit) or httpx.InvalidURL; both are
        # the Agent's mistake, not a failure of the system, so they are refusals.
        except (ValueError, httpx.InvalidURL) as exc:
            return self._refused(intent, f"web could not read the URL: {exc.__class__.__name__}")
        except (httpx.HTTPError, TimeoutError) as exc:
            return CapabilityResult(
                capability=CAPABILITY, action=intent.action, ok=False,
                error={"code": "WEB_REQUEST_FAILED", "detail": exc.__class__.__name__},
            )
        return CapabilityResult(capability=CAPABILITY, action=intent.action, ok=True, data=data)

    @staticmethod
    def _refused(intent: CapabilityIntent, detail: str) -> CapabilityResult:
        return CapabilityResult(
            capability=CAPABILITY, action=intent.action, ok=False,
            error={"code": "WEB_REJECTED", "detail": detail},
        )

    @staticmethod
    def _allowed_hosts(context: CapabilityContext) -> list[str] | None:
        """The hosts the Creator narrowed this Mission to, when they narrowed it."""
        configured = context.authorization.scope.get("web_allowed_hosts")
        if configured is None:
            return None
        if isinstance(configured, str):
            configured = [configured]
        if not isinstance(configured, list):
            # A restriction that cannot be read is never treated as "no restriction".
            raise WebError("web host restriction could not be read")
        return [str(host).strip().lower() for host in configured if str(host).strip()]

    async def _checked_url(self, raw: str | None, allowed_hosts: list[str] | None) -> str:
        url = (raw or "").strip()
        if not url:
            raise WebError("web requires a resource URL")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            raise WebError("web supports only http and https")
        host = parts.hostname
        if not host:
            raise WebError("web requires a URL with a host")
        if allowed_hosts is not None and host.lower() not in allowed_hosts:
            raise WebError(f"web host is not in the authorized list: {host}")
        try:
            addresses = await self._resolve(host)
        except socket.gaierror as exc:
            raise WebError("web host could not be resolved") from exc
        if not addresses:
            raise WebError("web host could not be resolved")
        for address in addresses:
            _public_address(address)
        return url

    @staticmethod
    def _reached_address(response: httpx.Response) -> str | None:
        """The address the connection actually reached, when the transport reports one."""
        stream = response.extensions.get("network_stream")
        if stream is None:
            return None
        try:
            server = stream.get_extra_info("server_addr")
        except Exception:  # a transport that does not carry the detail
            return None
        if isinstance(server, (tuple, list)) and server:
            return str(server[0])
        return None

    async def _body(self, response: httpx.Response) -> tuple[str, bool]:
        """The page, stopped at the size limit rather than read whole into memory."""
        collected = bytearray()
        async for chunk in response.aiter_bytes():
            collected.extend(chunk)
            if len(collected) > self._max_bytes:
                break
        truncated = len(collected) > self._max_bytes
        body = bytes(collected[: self._max_bytes])
        return body.decode(response.encoding or "utf-8", errors="replace"), truncated

    async def _fetch(self, intent: CapabilityIntent, context: CapabilityContext) -> dict:
        allowed = self._allowed_hosts(context)
        url = await self._checked_url(intent.resource, allowed)

        # Redirects are followed by hand so every hop is checked; an open redirect to a
        # private address is the usual way past a check done only on the first URL.
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport, follow_redirects=False,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                request = client.build_request(
                    "GET", url, headers={"accept": "text/*, application/json"},
                )
                response = await client.send(request, stream=True)
                try:
                    reached = self._reached_address(response)
                    if reached is not None:
                        # The name resolved to a public address; this is where it landed.
                        _public_address(reached)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise WebError("web redirect had no destination")
                        url = await self._checked_url(str(response.url.join(location)), allowed)
                        continue

                    content, truncated = await self._body(response)
                    return {
                        "url": str(response.url),
                        "status": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "truncated": truncated,
                        "content": content,
                    }
                finally:
                    await response.aclose()
        raise WebError("web followed too many redirects")
