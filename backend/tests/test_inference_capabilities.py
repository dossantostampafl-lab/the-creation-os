from __future__ import annotations

import pytest

from app.inference.contracts import (
    InferenceRequest,
    InferenceResponse,
    ModelRequirements,
    ProviderHealth,
    ProviderModelProfile,
    ProviderUnavailable,
)
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


class CapabilityStubProvider:
    def __init__(self, name: str, *, healthy: bool = True) -> None:
        self.name = name
        self.healthy = healthy
        self.requests: list[InferenceRequest] = []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        return InferenceResponse(
            provider=self.name,
            model=request.model or f"{self.name}-default",
            content="ok",
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=self.healthy)


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_provider_model_profile() -> None:
    registry = ProviderRegistry()
    registry.register(CapabilityStubProvider("primary"))
    profile = ProviderModelProfile(
        provider="primary",
        model="model-a",
        capabilities={"text", "streaming"},
        is_default=True,
    )
    registry.register_model_profile(profile)

    with pytest.raises(ValueError, match="profile already registered"):
        registry.register_model_profile(profile)


@pytest.mark.asyncio
async def test_registry_rejects_second_default_model_for_provider() -> None:
    registry = ProviderRegistry()
    registry.register(CapabilityStubProvider("primary"))
    registry.register_model_profile(
        ProviderModelProfile(
            provider="primary",
            model="model-a",
            capabilities={"text"},
            is_default=True,
        )
    )

    with pytest.raises(ValueError, match="default model already registered"):
        registry.register_model_profile(
            ProviderModelProfile(
                provider="primary",
                model="model-b",
                capabilities={"text", "vision"},
                is_default=True,
            )
        )


@pytest.mark.asyncio
async def test_router_preserves_existing_behavior_when_no_capabilities_requested() -> None:
    registry = ProviderRegistry()
    primary = CapabilityStubProvider("primary")
    registry.register(primary)
    router = ModelRouter(registry)

    response = await router.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            requirements=ModelRequirements(preferred_provider="primary"),
        )
    )

    assert response.provider == "primary"
    assert len(primary.requests) == 1


@pytest.mark.asyncio
async def test_router_admits_default_model_when_capability_evidence_matches() -> None:
    registry = ProviderRegistry()
    primary = CapabilityStubProvider("primary")
    registry.register(primary)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="primary",
            model="primary-default",
            capabilities={"text", "streaming"},
            is_default=True,
        )
    )
    router = ModelRouter(registry)

    response = await router.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            requirements=ModelRequirements(
                preferred_provider="primary",
                required_capabilities={"text"},
            ),
        )
    )

    assert response.provider == "primary"
    assert len(primary.requests) == 1


@pytest.mark.asyncio
async def test_router_fails_closed_when_required_capability_has_no_evidence() -> None:
    registry = ProviderRegistry()
    primary = CapabilityStubProvider("primary")
    registry.register(primary)
    router = ModelRouter(registry)

    with pytest.raises(ProviderUnavailable, match="capability evidence"):
        await router.generate(
            InferenceRequest(
                messages=[{"role": "user", "content": "hello"}],
                requirements=ModelRequirements(
                    preferred_provider="primary",
                    required_capabilities={"vision"},
                ),
            )
        )

    assert primary.requests == []


@pytest.mark.asyncio
async def test_router_uses_only_explicit_fallback_when_primary_lacks_capability() -> None:
    registry = ProviderRegistry()
    primary = CapabilityStubProvider("primary")
    fallback = CapabilityStubProvider("fallback")
    unrelated = CapabilityStubProvider("unrelated")
    registry.register(primary)
    registry.register(fallback)
    registry.register(unrelated)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="primary",
            model="primary-default",
            capabilities={"text"},
            is_default=True,
        )
    )
    registry.register_model_profile(
        ProviderModelProfile(
            provider="fallback",
            model="fallback-default",
            capabilities={"text", "vision"},
            is_default=True,
        )
    )
    registry.register_model_profile(
        ProviderModelProfile(
            provider="unrelated",
            model="unrelated-default",
            capabilities={"text", "vision"},
            is_default=True,
        )
    )
    router = ModelRouter(registry)

    response = await router.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            requirements=ModelRequirements(
                preferred_provider="primary",
                fallback_providers=["fallback"],
                required_capabilities={"vision"},
            ),
        )
    )

    assert response.provider == "fallback"
    assert primary.requests == []
    assert len(fallback.requests) == 1
    assert unrelated.requests == []


@pytest.mark.asyncio
async def test_router_checks_explicit_request_model_capabilities() -> None:
    registry = ProviderRegistry()
    primary = CapabilityStubProvider("primary")
    registry.register(primary)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="primary",
            model="text-model",
            capabilities={"text"},
            is_default=True,
        )
    )
    registry.register_model_profile(
        ProviderModelProfile(
            provider="primary",
            model="vision-model",
            capabilities={"text", "vision"},
        )
    )
    router = ModelRouter(registry)

    response = await router.generate(
        InferenceRequest(
            messages=[{"role": "user", "content": "inspect"}],
            model="vision-model",
            requirements=ModelRequirements(
                preferred_provider="primary",
                required_capabilities={"vision"},
            ),
        )
    )

    assert response.model == "vision-model"
    assert len(primary.requests) == 1


@pytest.mark.asyncio
async def test_router_rejects_explicit_model_without_required_capability() -> None:
    registry = ProviderRegistry()
    primary = CapabilityStubProvider("primary")
    registry.register(primary)
    registry.register_model_profile(
        ProviderModelProfile(
            provider="primary",
            model="text-model",
            capabilities={"text"},
            is_default=True,
        )
    )
    router = ModelRouter(registry)

    with pytest.raises(ProviderUnavailable, match="required capabilities"):
        await router.generate(
            InferenceRequest(
                messages=[{"role": "user", "content": "inspect"}],
                model="text-model",
                requirements=ModelRequirements(
                    preferred_provider="primary",
                    required_capabilities={"vision"},
                ),
            )
        )

    assert primary.requests == []
