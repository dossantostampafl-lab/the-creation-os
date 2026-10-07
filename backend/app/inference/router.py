from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Collection, Sequence

from loguru import logger

from app.inference.contracts import (
    CostTier,
    InferenceAuthenticationError,
    InferenceBudgetError,
    InferenceError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceResponse,
    InferenceTimeoutError,
    ProviderUnavailable,
)
from app.inference.health import ProviderCircuitBreaker, ProviderRateLimitCooldown
from app.inference.registry import ProviderRegistry
from app.observability.telemetry import operation, traced


class ModelRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        circuit_breaker: ProviderCircuitBreaker | None = None,
        rate_limit_cooldown: ProviderRateLimitCooldown | None = None,
        rate_limit_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        fallback_providers: Sequence[str] = (),
        disclosed_fallback_after: Collection[str] = (),
    ) -> None:
        if rate_limit_cooldown_seconds < 0:
            raise ValueError("rate_limit_cooldown_seconds must be >= 0")
        self.registry = registry
        self._circuit_breaker = circuit_breaker or ProviderCircuitBreaker()
        self._rate_limit_cooldown = rate_limit_cooldown or ProviderRateLimitCooldown()
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._clock = clock
        # Last-resort providers tried after everything a request asked for is unavailable.
        self._fallback_providers = tuple(fallback_providers)
        # Providers whose failure may advance to the next candidate only because the operator
        # opted in and every such answer carries fallback_from/fallback_reason for the UI.
        self._disclosed_fallback_after = frozenset(
            name.strip().lower() for name in disclosed_fallback_after
        )

    def _must_stop_after_provider_failure(self, provider_name: str) -> bool:
        # OpenAI SIWC forbids silently moving a ChatGPT-plan request to another provider or
        # billing path. Without an explicit, disclosed fallback the request stops here.
        name = provider_name.strip().lower()
        return name == "chatgpt" and name not in self._disclosed_fallback_after

    def allows_fallback_after(self, provider_name: str) -> bool:
        return not self._must_stop_after_provider_failure(provider_name)

    @staticmethod
    def _attempt_timeout(provider_name: str, metadata: dict) -> float | None:
        by_provider = metadata.get("attempt_timeout_seconds_by_provider")
        value = (
            by_provider.get(provider_name)
            if isinstance(by_provider, dict) and provider_name in by_provider
            else metadata.get("attempt_timeout_seconds")
        )
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
        return None

    def _profile_for_request(self, provider_name: str, request: InferenceRequest):
        if request.model is not None:
            return self.registry.get_model_profile(provider_name, request.model)
        return self.registry.get_default_model_profile(provider_name)

    def _candidate_names(self, request: InferenceRequest) -> list[str]:
        requirements = request.requirements
        candidates: list[str] = []
        if requirements.preferred_provider:
            candidates.append(requirements.preferred_provider)
        candidates.extend(name for name in requirements.fallback_providers if name not in candidates)
        if requirements.routing_strategy == "benchmark":
            candidates = self._rank_by_benchmark(candidates, request)
        return candidates + [name for name in self._fallback_providers if name not in candidates]

    def _rank_by_benchmark(self, candidates: list[str], request: InferenceRequest) -> list[str]:
        ranked: list[tuple[int, float, int, str]] = []
        for index, provider_name in enumerate(candidates):
            profile = self._profile_for_request(provider_name, request)
            evidence = None
            if profile is not None:
                evidence = self.registry.get_benchmark_evidence(provider_name, profile.model)
            if evidence is None:
                ranked.append((1, 0.0, index, provider_name))
            else:
                ranked.append((0, -evidence.score, index, provider_name))
        ranked.sort()
        return [item[3] for item in ranked]

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

    def _request_for(self, provider_name: str, request: InferenceRequest) -> InferenceRequest:
        """A last-resort fallback serves its own default model when it does not know the requested one."""
        requested = {request.requirements.preferred_provider, *request.requirements.fallback_providers}
        if (
            provider_name in requested
            or provider_name not in self._fallback_providers
            or request.model is None
            or self.registry.get_model_profile(provider_name, request.model) is not None
        ):
            return request
        return request.model_copy(update={"model": None})

    @traced("llm.generate")
    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        candidates = self._candidate_names(request)
        if not candidates:
            raise ProviderUnavailable("router", "no inference provider requested")

        last_error: InferenceError | None = None
        first_failure: InferenceError | None = None
        for provider_name in candidates:
            if last_error is not None and first_failure is None:
                first_failure = last_error
            provider = self.registry.get(provider_name)
            attempt = self._request_for(provider_name, request)

            # Creation-owned governance gates fail closed and cannot be bypassed
            # by advancing to another candidate.
            self._admit_capabilities(provider_name, attempt)
            self._admit_budget(provider_name, attempt)

            now = self._clock()
            if not self._rate_limit_cooldown.can_attempt(provider_name, now=now):
                last_error = ProviderUnavailable(provider_name, "provider rate-limit cooldown active")
                if self._must_stop_after_provider_failure(provider_name):
                    raise last_error
                continue
            if not self._circuit_breaker.can_attempt(provider_name, now=now):
                last_error = ProviderUnavailable(provider_name, "provider circuit open")
                if self._must_stop_after_provider_failure(provider_name):
                    raise last_error
                continue

            try:
                with operation("llm.attempt", {"creation.provider": provider_name}):
                    # Interactive DEUS turns skip the redundant preflight network call. Provider
                    # generation already reports timeout/rate-limit/unavailable failures and the
                    # circuit-breaker/fallback path below handles them without a second round trip.
                    if not bool(attempt.metadata.get("skip_health_probe")):
                        health = await provider.health()
                        if not health.available:
                            raise ProviderUnavailable(provider_name, health.detail or "provider unavailable")
                    timeout_seconds = self._attempt_timeout(provider_name, attempt.metadata)
                    if timeout_seconds is not None:
                        try:
                            async with asyncio.timeout(timeout_seconds):
                                response = await provider.generate(attempt)
                        except TimeoutError as exc:
                            raise InferenceTimeoutError(
                                provider_name,
                                f"{provider_name} exceeded the interactive attempt deadline",
                            ) from exc
                    else:
                        response = await provider.generate(attempt)
            except InferenceRateLimitError as exc:
                self._rate_limit_cooldown.register(
                    provider_name,
                    now=self._clock(),
                    retry_after_seconds=self._rate_limit_cooldown_seconds,
                )
                last_error = exc
                if self._must_stop_after_provider_failure(provider_name):
                    raise
                continue
            except InferenceTimeoutError as exc:
                self._circuit_breaker.record_transient_failure(provider_name, now=self._clock())
                last_error = exc
                if self._must_stop_after_provider_failure(provider_name):
                    raise
                continue
            except InferenceAuthenticationError as exc:
                # Credential failures are logged without their secret. ChatGPT-plan requests stop
                # here; other providers retain the configured reserve behavior.
                logger.warning(
                    "inference provider {} refused its credential; trying the next provider if there is one",
                    provider_name,
                )
                self._circuit_breaker.record_transient_failure(provider_name, now=self._clock())
                last_error = exc
                if self._must_stop_after_provider_failure(provider_name):
                    raise
                continue
            except ProviderUnavailable as exc:
                self._circuit_breaker.record_transient_failure(provider_name, now=self._clock())
                last_error = exc
                if self._must_stop_after_provider_failure(provider_name):
                    raise
                continue

            self._circuit_breaker.record_success(provider_name)
            if first_failure is not None:
                # The answer came from a later candidate: say which provider failed and why,
                # so the reply is never presented as if the first choice had produced it.
                response = response.model_copy(
                    update={
                        "metadata": {
                            **response.metadata,
                            "fallback_from": first_failure.provider,
                            "fallback_reason": first_failure.upstream_code or first_failure.code,
                        }
                    }
                )
            return response

        if last_error is not None:
            raise last_error
        raise ProviderUnavailable("router", "no inference provider available")
