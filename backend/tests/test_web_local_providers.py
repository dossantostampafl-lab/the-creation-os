from __future__ import annotations

import asyncio

import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, MissionAuthorization
from app.capabilities.web_providers import (
    CallableWebProvider,
    Crawl4AIProvider,
    CrawleeProvider,
    ProviderLimits,
    ProviderUnavailable,
    WebProviderMetadata,
)


def _context() -> CapabilityContext:
    return CapabilityContext(
        mission_id="mission-local-provider",
        authorization=MissionAuthorization(
            allowed_capabilities=["web"],
            authorized_by="creator",
            authorized_at="2026-09-27T00:00:00Z",
        ),
    )


def _intent(action: str) -> CapabilityIntent:
    return CapabilityIntent(capability="web", action=action, resource="https://example.com")


@pytest.mark.asyncio
async def test_crawlee_and_crawl4ai_contracts_are_optional_and_fail_closed_without_runner() -> None:
    with pytest.raises(ProviderUnavailable):
        await CrawleeProvider().execute(_intent("crawl"), _context())
    with pytest.raises(ProviderUnavailable):
        await Crawl4AIProvider().execute(_intent("extract"), _context())


@pytest.mark.asyncio
async def test_provider_page_and_byte_budgets_are_enforced() -> None:
    async def pages(intent, context):
        return {"pages": [{"url": f"https://example.com/{index}"} for index in range(5)]}

    provider = CallableWebProvider(
        name="bounded",
        actions=("crawl",),
        runner=pages,
        metadata=WebProviderMetadata(
            origin="local:test",
            license="test",
            security_review="approved",
            supported_actions=frozenset({"crawl"}),
            shadow_enabled=True,
            production_enabled=True,
        ),
        limits=ProviderLimits(timeout_seconds=1, max_pages=2, max_bytes=10_000),
    )
    data = await provider.execute(_intent("crawl"), _context())
    assert len(data["pages"]) == 2
    assert data["truncated"] is True

    async def oversized(intent, context):
        return {"content": "x" * 500}

    too_large = CallableWebProvider(
        name="too-large",
        actions=("extract",),
        runner=oversized,
        metadata=provider.metadata,
        limits=ProviderLimits(timeout_seconds=1, max_pages=2, max_bytes=100),
    )
    with pytest.raises(ProviderUnavailable, match="byte budget"):
        await too_large.execute(_intent("extract"), _context())


@pytest.mark.asyncio
async def test_provider_timeout_is_classified_unavailable_and_cancellation_propagates() -> None:
    async def slow(intent, context):
        await asyncio.sleep(1)
        return {}

    provider = CallableWebProvider(
        name="slow",
        actions=("crawl",),
        runner=slow,
        metadata=WebProviderMetadata(
            origin="local:test",
            license="test",
            security_review="approved",
            supported_actions=frozenset({"crawl"}),
            shadow_enabled=True,
            production_enabled=True,
        ),
        limits=ProviderLimits(timeout_seconds=0.01, max_pages=2, max_bytes=1000),
    )
    with pytest.raises(ProviderUnavailable, match="timed out"):
        await provider.execute(_intent("crawl"), _context())

    started = asyncio.Event()

    async def cancellable(intent, context):
        started.set()
        await asyncio.sleep(60)
        return {}

    cancellable_provider = CallableWebProvider(
        name="cancellable",
        actions=("crawl",),
        runner=cancellable,
        metadata=provider.metadata,
        limits=ProviderLimits(timeout_seconds=120, max_pages=2, max_bytes=1000),
    )
    task = asyncio.create_task(cancellable_provider.execute(_intent("crawl"), _context()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
