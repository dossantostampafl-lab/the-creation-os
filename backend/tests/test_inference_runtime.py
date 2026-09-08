from __future__ import annotations

import pytest

from app.inference.contracts import (
    InferenceRequest,
    InferenceResponse,
    ModelRequirements,
    ProviderHealth,
    ProviderUnavailable,
)
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


class StubProvider:
    def __init__(self, name: str, *, healthy: bool = True) -> None:
        self.name = name
        self.healthy = healthy
        self.requests: list[InferenceRequest] = []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        if not self.healthy:
            raise ProviderUnavailable(self.name, "provider unavailable")
        return InferenceResponse(
            provider=self.name,
            model=request.model or "stub-model",
            content="ok",
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=self.healthy)


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_provider_names() -> None:
    registry = ProviderRegistry()
    registry.register(StubProvider("primary"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(StubProvider("primary"))


@pytest.mark.asyncio
async def test_router_uses_requested_provider_without_silent_fake_fallback() -> None:
    registry = ProviderRegistry()
    primary = StubProvider("primary")
    fallback = StubProvider("fallback")
    registry.register(primary)
    registry.register(fallback)
    router = ModelRouter(registry)
    request = InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        requirements=ModelRequirements(preferred_provider="primary"),
    )

    response = await router.generate(request)

    assert response.provider == "primary"
    assert len(primary.requests) == 1
    assert fallback.requests == []


@pytest.mark.asyncio
async def test_router_fallback_requires_explicit_allowlist() -> None:
    registry = ProviderRegistry()
    registry.register(StubProvider("primary", healthy=False))
    registry.register(StubProvider("fallback"))
    router = ModelRouter(registry)

    with pytest.raises(ProviderUnavailable):
        await router.generate(
            InferenceRequest(
                messages=[{"role": "user", "content": "hello"}],
                requirements=ModelRequirements(preferred_provider="primary"),
            )
        )

    response = await router.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            requirements=ModelRequirements(
                preferred_provider="primary",
                fallback_providers=["fallback"],
            ),
        )
    )
    assert response.provider == "fallback"
