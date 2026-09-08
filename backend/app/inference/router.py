from __future__ import annotations

from app.inference.contracts import InferenceRequest, InferenceResponse, ProviderUnavailable
from app.inference.registry import ProviderRegistry


class ModelRouter:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        requirements = request.requirements
        candidates: list[str] = []
        if requirements.preferred_provider:
            candidates.append(requirements.preferred_provider)
        candidates.extend(name for name in requirements.fallback_providers if name not in candidates)
        if not candidates:
            raise ProviderUnavailable("router", "no inference provider requested")

        last_error: ProviderUnavailable | None = None
        for provider_name in candidates:
            try:
                provider = self.registry.get(provider_name)
                health = await provider.health()
                if not health.available:
                    raise ProviderUnavailable(provider_name, health.detail or "provider unavailable")
                return await provider.generate(request)
            except ProviderUnavailable as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ProviderUnavailable("router", "no inference provider available")
