from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from app.inference.bootstrap import build_model_router
from app.inference.router import ModelRouter


class InferenceModelStatus(BaseModel):
    model: str
    is_default: bool
    capabilities: list[str] = Field(default_factory=list)
    cost_tier: str


class InferenceProviderStatus(BaseModel):
    provider: str
    available: bool
    detail: str | None = None
    models: list[InferenceModelStatus] = Field(default_factory=list)


class InferenceStatusSnapshot(BaseModel):
    configured: bool
    configured_provider: str
    providers: list[InferenceProviderStatus] = Field(default_factory=list)


async def build_inference_status(router: ModelRouter) -> InferenceStatusSnapshot:
    provider_names = router.registry.names()
    statuses: list[InferenceProviderStatus] = []
    for provider_name in provider_names:
        provider = router.registry.get(provider_name)
        try:
            health = await provider.health()
            available = bool(health.available)
            detail = health.detail
        except Exception:
            available = False
            detail = "health_probe_failed"

        models = [
            InferenceModelStatus(
                model=profile.model,
                is_default=profile.is_default,
                capabilities=sorted(profile.capabilities),
                cost_tier=profile.cost_tier.name,
            )
            for profile in router.registry.model_profiles(provider_name)
        ]
        statuses.append(
            InferenceProviderStatus(
                provider=provider_name,
                available=available,
                detail=detail,
                models=models,
            )
        )

    return InferenceStatusSnapshot(
        configured=bool(provider_names),
        configured_provider=provider_names[0] if provider_names else "",
        providers=statuses,
    )


async def configured_inference_status(
    provider_name: str,
    *,
    router_factory: Callable[[], ModelRouter] = build_model_router,
) -> InferenceStatusSnapshot:
    normalized = provider_name.strip().lower()
    if normalized in {"", "fake"}:
        return InferenceStatusSnapshot(
            configured=False,
            configured_provider=normalized,
            providers=[],
        )

    try:
        router = router_factory()
    except Exception:
        return InferenceStatusSnapshot(
            configured=False,
            configured_provider=normalized,
            providers=[],
        )

    snapshot = await build_inference_status(router)
    return snapshot.model_copy(update={"configured_provider": normalized})
