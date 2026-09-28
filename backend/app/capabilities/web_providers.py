from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from app.capabilities.contracts import CapabilityContext, CapabilityIntent


class ProviderUnavailable(RuntimeError):
    """A provider cannot serve this request now; another eligible provider may be tried."""


class NoWebProvider(LookupError):
    """No configured provider can serve the requested logical web action."""


@dataclass(frozen=True)
class WebProviderMetadata:
    origin: str
    license: str
    security_review: str
    supported_actions: frozenset[str]
    shadow_enabled: bool = False
    production_enabled: bool = False
    health: str = "healthy"
    cost: float = 0.0
    latency_ms: float = 0.0
    success_rate: float = 1.0

    @property
    def certified(self) -> bool:
        return self.security_review.strip().lower() in {"approved", "certified", "passed"}


@runtime_checkable
class WebProvider(Protocol):
    name: str
    actions: frozenset[str]
    metadata: WebProviderMetadata

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> dict[str, Any]: ...


def _provider_order(
    providers: Sequence[WebProvider],
    preferred: list[str] | None,
) -> list[WebProvider]:
    preferred = [name.strip().lower() for name in (preferred or []) if name.strip()]
    rank = {name: index for index, name in enumerate(preferred)}
    indexed = list(enumerate(providers))
    indexed.sort(key=lambda item: (rank.get(item[1].name.lower(), len(rank)), item[0]))
    return [provider for _, provider in indexed]


def provider_eligible(
    provider: WebProvider,
    *,
    action: str,
    material: bool = False,
) -> bool:
    metadata = provider.metadata
    if action not in provider.actions or action not in metadata.supported_actions:
        return False
    if metadata.health.strip().lower() not in {"healthy", "degraded"}:
        return False
    if material:
        return metadata.production_enabled and metadata.certified
    return metadata.production_enabled or metadata.shadow_enabled


def select_web_provider(
    action: str,
    providers: Sequence[WebProvider],
    *,
    preferred: list[str] | None = None,
    material: bool = False,
) -> WebProvider:
    for provider in _provider_order(providers, preferred):
        if provider_eligible(provider, action=action, material=material):
            return provider
    raise NoWebProvider(f"no eligible web provider for action: {action}")


def web_provider_candidates(
    action: str,
    providers: Sequence[WebProvider],
    *,
    preferred: list[str] | None = None,
    material: bool = False,
) -> list[WebProvider]:
    return [
        provider
        for provider in _provider_order(providers, preferred)
        if provider_eligible(provider, action=action, material=material)
    ]


ProviderRunner = Callable[[CapabilityIntent, CapabilityContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ProviderLimits:
    timeout_seconds: float = 15.0
    max_pages: int = 20
    max_bytes: int = 500_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.max_pages <= 0 or self.max_bytes <= 0:
            raise ValueError("provider limits must be positive")


def _bounded_payload(data: dict[str, Any], limits: ProviderLimits) -> dict[str, Any]:
    normalized = dict(data)
    pages = normalized.get("pages")
    if isinstance(pages, list) and len(pages) > limits.max_pages:
        normalized["pages"] = pages[: limits.max_pages]
        normalized["truncated"] = True
    encoded = json.dumps(normalized, default=str, ensure_ascii=False).encode("utf-8")
    if len(encoded) > limits.max_bytes:
        raise ProviderUnavailable("provider response exceeds byte budget")
    return normalized


class CallableWebProvider:
    """Small adapter contract used for local libraries, MCP tools, and deterministic tests."""

    def __init__(
        self,
        *,
        name: str,
        actions: Sequence[str],
        runner: ProviderRunner | None,
        metadata: WebProviderMetadata,
        limits: ProviderLimits | None = None,
    ) -> None:
        self.name = name
        self.actions = frozenset(actions)
        self._runner = runner
        self.metadata = metadata
        self.limits = limits or ProviderLimits()

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> dict[str, Any]:
        if intent.action not in self.actions:
            raise ProviderUnavailable(f"{self.name} does not support {intent.action}")
        if self._runner is None:
            raise ProviderUnavailable(f"{self.name} is not configured")
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                data = await self._runner(intent, context)
        except TimeoutError as exc:
            raise ProviderUnavailable(f"{self.name} timed out") from exc
        if not isinstance(data, dict):
            raise ProviderUnavailable(f"{self.name} returned malformed data")
        return _bounded_payload(data, self.limits)


class CrawleeProvider(CallableWebProvider):
    """Optional local Crawlee adapter. The runner owns the library/process integration."""

    def __init__(self, runner: ProviderRunner | None = None) -> None:
        super().__init__(
            name="crawlee",
            actions=("crawl",),
            runner=runner,
            metadata=WebProviderMetadata(
                origin="local:crawlee",
                license="Apache-2.0",
                security_review="approved",
                supported_actions=frozenset({"crawl"}),
                shadow_enabled=True,
                production_enabled=True,
            ),
        )


class Crawl4AIProvider(CallableWebProvider):
    """Optional local Crawl4AI adapter for extraction/crawl; absent runner fails closed."""

    def __init__(self, runner: ProviderRunner | None = None) -> None:
        super().__init__(
            name="crawl4ai",
            actions=("crawl", "extract"),
            runner=runner,
            metadata=WebProviderMetadata(
                origin="local:crawl4ai",
                license="Apache-2.0",
                security_review="approved",
                supported_actions=frozenset({"crawl", "extract"}),
                shadow_enabled=True,
                production_enabled=True,
            ),
        )


class RemoteContractWebProvider:
    """Configuration-gated remote provider behind the stable Creation web contract.

    This adapter intentionally does not grant authority. It only translates an already
    authorized logical web action to a configured provider endpoint.
    """

    def __init__(
        self,
        *,
        name: str,
        endpoint: str | None,
        actions: Sequence[str],
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        metadata: WebProviderMetadata,
    ) -> None:
        self.name = name
        self.actions = frozenset(actions)
        self.endpoint = (endpoint or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.metadata = metadata

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> dict[str, Any]:
        if intent.action not in self.actions:
            raise ProviderUnavailable(f"{self.name} does not support {intent.action}")
        if not self.endpoint:
            raise ProviderUnavailable(f"{self.name} endpoint is not configured")

        headers = {"accept": "application/json", "content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        payload = {
            "action": intent.action,
            "resource": intent.resource,
            "arguments": intent.arguments,
            "mission_id": context.mission_id,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
        except (httpx.HTTPError, TimeoutError) as exc:
            raise ProviderUnavailable(f"{self.name} unavailable: {exc.__class__.__name__}") from exc
        if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
            raise ProviderUnavailable(f"{self.name} unavailable: HTTP {response.status_code}")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderUnavailable(f"{self.name} returned a malformed response")
        return data


MCPCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class MCPWebProvider:
    """Certified MCP adapter contract; registry discovery alone never instantiates authority."""

    def __init__(
        self,
        *,
        name: str,
        tool_name: str,
        actions: Sequence[str],
        caller: MCPCaller | None,
        metadata: WebProviderMetadata,
    ) -> None:
        self.name = name
        self.tool_name = tool_name
        self.actions = frozenset(actions)
        self._caller = caller
        self.metadata = metadata

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> dict[str, Any]:
        if intent.action not in self.actions:
            raise ProviderUnavailable(f"{self.name} does not support {intent.action}")
        if self._caller is None:
            raise ProviderUnavailable(f"{self.name} MCP transport is not configured")
        data = await self._caller(
            self.tool_name,
            {
                "action": intent.action,
                "resource": intent.resource,
                "arguments": intent.arguments,
                "mission_id": context.mission_id,
            },
        )
        if not isinstance(data, dict):
            raise ProviderUnavailable(f"{self.name} returned a malformed MCP response")
        return data
