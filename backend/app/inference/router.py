from __future__ import annotations

import time
from collections.abc import Callable

from app.inference.contracts import (
    CostTier,
    InferenceBudgetError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceTimeoutError,
    ProviderUnavailable,
)
from app.inference.health import ProviderCircuitBreaker, ProviderRateLimitCooldown
from app.inference.registry import ProviderRegistry


class ModelRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        circuit_breaker: ProviderCircuitBreaker | None = None,
        rate_limit_cooldown: ProviderRateLimitCooldown | None = None,
        rate_limit_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_limit_cooldown_seconds < 0:
            raise ValueError("rate_limit_cooldown_seconds must be >= 0")
        self.registry = registry
        self._circuit_breaker = circuit_breaker or ProviderCircuitBreaker()
        self._rate_limit_cooldown = rate_limit_cooldown or ProviderRateLimitCooldown()
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._clock = clock

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
            provider = self.registry.get(provider_name)

            # Governance gates fail closed. A candidate that lacks Creation-owned
            # capability or budget evidence must not be bypassed by fallback.
            self._admit_capabilities(provider_name, request)
            self._admit_budget(provider_name, request)

            now = self._clock()
            if not self._rate_limit_cooldown.can_attempt(provider_name, now=now):
                last_error = ProviderUnavailable(provider_name, "provider rate-limit cooldown active")
                continue
            if not self._circuit_breaker.can_attempt(provider_name, now=now):
                last_error = ProviderUnavailable(provider_name, "provider circuit open")
                continue

            try:
                health = await provider.health()
                if not health.available:
                    raise ProviderUnavailable(provider_name, health.detail or "provider unavailable")
                response = await provider.generate(request)
            except InferenceRateLimitError as exc:
                self._rate_limit_cooldown.register(
                    provider_name,
                    now=self._clock(),
                    retry_after_seconds=self._rate_limit_cooldown_seconds,
                )
                last_error = exc
                continue
            except InferenceTimeoutError as exc:
                self._circuit_breaker.record_transient_failure(provider_name, now=self._clock())
                last_error = exc
                continue
            except ProviderUnavailable as exc:
                self._circuit_breaker.record_transient_failure(provider_name, now=self._clock())
                last_error = exc
                continue

            self._circuit_breaker.record_success(provider_name)
            return response

        if last_error is not None:
            raise last_error
        raise ProviderUnavailable("router", "no inference provider available")
