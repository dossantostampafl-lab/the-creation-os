from __future__ import annotations

import pytest

from app.cache.contracts import CacheDecision, CacheDecisionType, CachedResponsePayload, CacheLookupResult
from app.cache.routing import CachingModelRouter
from app.inference.contracts import InferenceRequest, InferenceResponse, ModelRequirements, ProviderHealth
from app.inference.registry import ProviderRegistry


class StubProvider:
    name = "primary"

    def __init__(self) -> None:
        self.calls = 0

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
        return InferenceResponse(provider=self.name, model=request.model or "model-a", content="fresh")


class StubCache:
    def __init__(self, lookup: CacheLookupResult | Exception) -> None:
        self.lookup_value = lookup
        self.admissions = 0
        self.aborts = 0

    async def lookup(self, request: InferenceRequest) -> CacheLookupResult:
        if isinstance(self.lookup_value, Exception):
            raise self.lookup_value
        return self.lookup_value

    async def admit(self, request, response, lookup) -> None:
        self.admissions += 1

    async def abort(self, lookup) -> None:
        self.aborts += 1


def request() -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "Explain the architecture"}],
        model="model-a",
        requirements=ModelRequirements(preferred_provider="primary"),
        metadata={"creator_id": "creator-a", "cache_intent": "EXPLANATION"},
    )


@pytest.mark.asyncio
async def test_router_short_circuits_provider_on_cache_hit() -> None:
    provider = StubProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    cache = StubCache(
        CacheLookupResult(
            decision=CacheDecision(decision=CacheDecisionType.HIT, reason="test_hit"),
            response=CachedResponsePayload(provider="cached-provider", model="cached-model", content="cached"),
        )
    )
    router = CachingModelRouter(registry, cache=cache)  # type: ignore[arg-type]

    response = await router.generate(request())

    assert response.content == "cached"
    assert response.metadata["cache"]["decision"] == "HIT"
    assert provider.calls == 0
    assert cache.admissions == 0


@pytest.mark.asyncio
async def test_router_cache_lookup_failure_is_fail_open() -> None:
    provider = StubProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    cache = StubCache(RuntimeError("cache unavailable"))
    router = CachingModelRouter(registry, cache=cache)  # type: ignore[arg-type]

    response = await router.generate(request())

    assert response.content == "fresh"
    assert provider.calls == 1
    assert cache.admissions == 1


@pytest.mark.asyncio
async def test_router_admits_provider_response_after_miss() -> None:
    provider = StubProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    cache = StubCache(CacheLookupResult(decision=CacheDecision(decision=CacheDecisionType.MISS, reason="miss")))
    router = CachingModelRouter(registry, cache=cache)  # type: ignore[arg-type]

    response = await router.generate(request())

    assert response.content == "fresh"
    assert provider.calls == 1
    assert cache.admissions == 1
