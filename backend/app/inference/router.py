from __future__ import annotations

from app.inference.contracts import (
    CostTier,
    InferenceBudgetError,
    InferenceRequest,
    InferenceResponse,
    ProviderUnavailable,
)
from app.inference.registry import ProviderRegistry


class ModelRouter:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def _profile_for_request(self, provider_name: str, request: InferenceRequest):
        if request.model is not None:
            return self.registry.get_model_profile(provider_name, request.model)
        return self.registry.get_default_model_profile(provider_name)

    def _admit_capabilities(self, provider_name: str, request: InferenceRequest) -> None:
        required = request.requirements.required_capabilities
        if not required:
            return

        profile = self._profile_for_request(provider_name, request)
        if profile is None:
            raise ProviderUnavailable(
                provider_name,
                f"capability evidence unavailable for provider: {provider_name}",
            )

        missing = required.difference(profile.capabilities)
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ProviderUnavailable(
                provider_name,
                f"required capabilities unavailable for provider {provider_name}: {missing_list}",
            )

    def _admit_budget(self, provider_name: str, request: InferenceRequest) -> None:
        ceiling = request.requirements.max_cost_tier
        if ceiling is None:
            return

        profile = self._profile_for_request(provider_name, request)
        if profile is None or profile.cost_tier == CostTier.UNKNOWN:
            raise InferenceBudgetError(
                provider_name,
                f"cost evidence unavailable for provider: {provider_name}",
            )
        if profile.cost_tier > ceiling:
            raise InferenceBudgetError(
                provider_name,
                f"budget ceiling excludes provider: {provider_name}",
            )

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
                self._admit_capabilities(provider_name, request)
                self._admit_budget(provider_name, request)
                health = await provider.health()
                if not health.available:
                    raise ProviderUnavailable(provider_name, health.detail or "provider unavailable")
                return await provider.generate(request)
            except ProviderUnavailable as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ProviderUnavailable("router", "no inference provider available")
