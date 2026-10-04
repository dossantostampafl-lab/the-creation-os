from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
)

_IDEMPOTENCY_RANK = {
    IdempotencyClass.SAFE: 0,
    IdempotencyClass.IDEMPOTENT: 1,
    IdempotencyClass.AT_MOST_ONCE: 2,
}


class ProviderUnavailable(RuntimeError):
    """A provider cannot serve the request; another eligible provider may be considered."""


@dataclass(frozen=True)
class CapabilityProviderMetadata:
    origin: str
    license: str
    security_review: str
    health: str = "healthy"
    cost: float = 0.0
    latency_ms: float = 0.0
    success_rate: float = 1.0
    shadow_enabled: bool = False
    production_enabled: bool = False

    @property
    def certified(self) -> bool:
        return self.security_review.strip().lower() in {"approved", "certified", "passed"}


class CapabilityProvider(Protocol):
    provider_name: str
    capability: str
    actions: frozenset[str]
    external_effect: bool
    minimum_idempotency_class: IdempotencyClass
    metadata: CapabilityProviderMetadata

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult: ...


def _eligible(provider: CapabilityProvider, *, action: str, material: bool) -> bool:
    metadata = provider.metadata
    if not metadata.origin.strip() or not metadata.license.strip() or not metadata.security_review.strip():
        return False
    if action not in provider.actions:
        return False
    if metadata.health.strip().lower() not in {"healthy", "degraded"}:
        return False
    if material:
        return metadata.production_enabled and metadata.certified
    return metadata.production_enabled or metadata.shadow_enabled


def _provider_sort_key(provider: CapabilityProvider, preferred: list[str]) -> tuple:
    rank = {name.strip().lower(): index for index, name in enumerate(preferred) if name.strip()}
    health_rank = 0 if provider.metadata.health.strip().lower() == "healthy" else 1
    return (
        rank.get(provider.provider_name.lower(), len(rank)),
        health_rank,
        -float(provider.metadata.success_rate),
        float(provider.metadata.cost),
        float(provider.metadata.latency_ms),
        provider.provider_name,
    )


class RoutedCapabilityAdapter:
    """One logical capability backed by replaceable, centrally selected providers."""

    def __init__(
        self,
        *,
        capability: str,
        providers: Sequence[CapabilityProvider],
        preferred_providers: list[str] | None = None,
    ) -> None:
        if not capability.strip():
            raise ValueError("logical capability is required")
        if not providers:
            raise ValueError("routed capability requires at least one provider")
        if any(provider.capability != capability for provider in providers):
            raise ValueError("all providers must implement the routed logical capability")

        names = [provider.provider_name for provider in providers]
        if len(set(names)) != len(names):
            raise ValueError("routed capability provider names must be unique")

        effects = {provider.external_effect for provider in providers}
        if len(effects) != 1:
            raise ValueError("providers for one logical capability must agree on external-effect semantics")

        self.name = capability
        self._providers = list(providers)
        self._preferred_providers = list(preferred_providers or [])
        self.external_effect = effects.pop()
        self.minimum_idempotency_class = max(
            (provider.minimum_idempotency_class for provider in providers),
            key=lambda value: _IDEMPOTENCY_RANK[value],
        )

    def candidates(self, intent: CapabilityIntent) -> list[CapabilityProvider]:
        material = self.external_effect or intent.external_effect
        eligible = [
            provider
            for provider in self._providers
            if _eligible(provider, action=intent.action, material=material)
        ]
        return sorted(eligible, key=lambda provider: _provider_sort_key(provider, self._preferred_providers))

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        candidates = self.candidates(intent)
        if not candidates:
            return CapabilityResult(
                capability=self.name,
                action=intent.action,
                ok=False,
                error={"code": "NO_ELIGIBLE_PROVIDER", "detail": "no certified provider can serve this capability"},
            )

        # External AT_MOST_ONCE effects must never fail over after an ambiguous attempt.
        failover_safe = (
            not self.external_effect
            and self.minimum_idempotency_class is not IdempotencyClass.AT_MOST_ONCE
        )
        last_error: ProviderUnavailable | None = None
        for provider in candidates:
            try:
                result = await provider.execute(intent, context)
            except ProviderUnavailable as exc:
                last_error = exc
                if not failover_safe:
                    raise
                continue

            data = dict(result.data)
            data.setdefault("provider", provider.provider_name)
            return result.model_copy(update={"capability": self.name, "data": data})

        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=False,
            error={
                "code": "ALL_PROVIDERS_UNAVAILABLE",
                "detail": last_error.__class__.__name__ if last_error else "unavailable",
            },
        )
