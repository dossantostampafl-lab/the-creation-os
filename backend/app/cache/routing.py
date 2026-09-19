from __future__ import annotations

from loguru import logger

from app.cache.contracts import CacheDecisionType, CacheLookupResult
from app.cache.orchestrator import CacheOrchestrator
from app.inference.contracts import InferenceRequest, InferenceResponse
from app.inference.router import ModelRouter
from app.inference.registry import ProviderRegistry


class CachingModelRouter(ModelRouter):
    """Decorates the existing provider router without weakening its governance/failover logic."""

    def __init__(self, registry: ProviderRegistry, *, cache: CacheOrchestrator | None, **kwargs) -> None:
        super().__init__(registry, **kwargs)
        self._semantic_cache = cache

    @staticmethod
    def _cached_response(lookup: CacheLookupResult) -> InferenceResponse:
        if lookup.response is None:
            raise ValueError("cache hit missing response payload")
        metadata = dict(lookup.response.metadata)
        metadata["cache"] = {
            "decision": lookup.decision.decision.value,
            "reason": lookup.decision.reason,
            "cache_entry_id": lookup.decision.cache_entry_id,
            "semantic_similarity": lookup.decision.semantic_similarity,
        }
        return InferenceResponse(
            provider=lookup.response.provider,
            model=lookup.response.model,
            content=lookup.response.content,
            finish_reason=lookup.response.finish_reason,
            usage=dict(lookup.response.usage),
            metadata=metadata,
        )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        lookup: CacheLookupResult | None = None
        if self._semantic_cache is not None:
            try:
                lookup = await self._semantic_cache.lookup(request)
            except Exception as exc:
                logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                    "cache lookup failed open"
                )

        if lookup is not None and lookup.decision.decision == CacheDecisionType.HIT and lookup.response is not None:
            return self._cached_response(lookup)

        try:
            response = await super().generate(request)
        except Exception:
            if self._semantic_cache is not None:
                await self._semantic_cache.abort(lookup)
            raise

        if self._semantic_cache is not None:
            try:
                await self._semantic_cache.admit(request, response, lookup)
            except Exception as exc:
                logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                    "cache admission failed open"
                )
                await self._semantic_cache.abort(lookup)
        return response
