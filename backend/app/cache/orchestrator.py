from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.interfaces import EmbeddingModel
from app.cache.contracts import (
    CacheContext,
    CacheDecision,
    CacheDecisionType,
    CachedResponsePayload,
    CacheLookupResult,
    CacheMode,
)
from app.cache.fingerprint import (
    build_authorization_fingerprint,
    build_context_hash,
    build_exact_key,
    build_generation_profile_hash,
    extract_last_user_query,
    normalize_query,
)
from app.cache.policy import evaluate_policy, ttl_seconds_for_intent
from app.cache.redis_store import RedisCacheStore
from app.cache.repository import CacheRepository
from app.inference.contracts import InferenceRequest, InferenceResponse
from app.repositories.domain import sanitize


_SAFE_METADATA_KEYS = {"cache", "finish_reason", "citations", "source_ids", "grounding"}


class CacheOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis_store: RedisCacheStore,
        *,
        embedding_model: EmbeddingModel | None,
        embedding_model_name: str,
        embedding_version: str,
        mode: CacheMode,
        policy_version: str,
        similarity_threshold: float,
        revalidate_threshold: float,
        max_candidates: int,
        default_ttl_seconds: int,
        document_ttl_seconds: int,
        deterministic_ttl_seconds: int,
        lock_seconds: int,
        singleflight_wait_ms: int,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis_store
        self.embedding_model = embedding_model
        self.embedding_model_name = embedding_model_name
        self.embedding_version = embedding_version
        self.mode = mode
        self.policy_version = policy_version
        self.similarity_threshold = similarity_threshold
        self.revalidate_threshold = revalidate_threshold
        self.max_candidates = max_candidates
        self.default_ttl_seconds = default_ttl_seconds
        self.document_ttl_seconds = document_ttl_seconds
        self.deterministic_ttl_seconds = deterministic_ttl_seconds
        self.lock_seconds = lock_seconds
        self.singleflight_wait_ms = singleflight_wait_ms

    async def _metric(self, name: str, amount: int = 1) -> None:
        try:
            await self.redis.increment(name, amount)
        except Exception as exc:
            logger.bind(component="semantic_cache", metric=name, error_type=exc.__class__.__name__).warning(
                "cache metrics backend unavailable"
            )

    @staticmethod
    def _payload(value: dict[str, Any]) -> CachedResponsePayload | None:
        try:
            return CachedResponsePayload.model_validate(value)
        except Exception:
            return None

    @staticmethod
    def _safe_response(response: InferenceResponse) -> CachedResponsePayload:
        metadata = {
            key: sanitize(value)
            for key, value in response.metadata.items()
            if key in _SAFE_METADATA_KEYS
        }
        return CachedResponsePayload(
            provider=response.provider,
            model=response.model,
            content=response.content,
            finish_reason=response.finish_reason,
            usage=dict(response.usage),
            metadata=metadata,
        )

    def _context(self, request: InferenceRequest, *, intent: Any, sensitivity: Any) -> CacheContext | None:
        creator_scope = request.metadata.get("creator_id")
        if not isinstance(creator_scope, str) or not creator_scope.strip():
            return None
        universe = request.metadata.get("universe_id")
        tags_raw = request.metadata.get("cache_tags", [])
        tags = tuple(str(tag) for tag in tags_raw) if isinstance(tags_raw, (list, tuple, set)) else ()
        return CacheContext(
            creator_scope=creator_scope.strip(),
            universe_scope=str(universe) if universe is not None else None,
            intent=intent,
            sensitivity=sensitivity,
            context_hash=build_context_hash(request),
            context_version=str(request.metadata["context_version"]) if request.metadata.get("context_version") is not None else None,
            knowledge_version=str(request.metadata["knowledge_version"]) if request.metadata.get("knowledge_version") is not None else None,
            retrieval_fingerprint=str(request.metadata["retrieval_fingerprint"]) if request.metadata.get("retrieval_fingerprint") is not None else None,
            generation_profile_hash=build_generation_profile_hash(request),
            policy_version=self.policy_version,
            authorization_fingerprint=build_authorization_fingerprint(request),
            tool_state_class=str(request.metadata.get("tool_state_class", "read_only")),
            tags=tags,
        )

    async def lookup(self, request: InferenceRequest) -> CacheLookupResult:
        started = datetime.now(timezone.utc)
        started_mono = time.perf_counter()
        await self._metric("cache_requests_total")
        if self.mode == CacheMode.OFF:
            await self._metric("cache_bypass_total")
            return CacheLookupResult(
                decision=CacheDecision(decision=CacheDecisionType.BYPASS, reason="cache_mode_off"),
                lookup_started_at=started,
            )

        query = extract_last_user_query(request)
        if not query:
            await self._metric("cache_bypass_total")
            return CacheLookupResult(
                decision=CacheDecision(decision=CacheDecisionType.BYPASS, reason="no_user_query"),
                lookup_started_at=started,
            )

        evaluation = evaluate_policy(request, query)
        normalized = normalize_query(query)
        if not evaluation.eligible:
            await self._metric("cache_bypass_total")
            return CacheLookupResult(
                decision=CacheDecision(decision=CacheDecisionType.BYPASS, reason=evaluation.reason),
                query=query,
                normalized_query=normalized,
                lookup_started_at=started,
            )

        context = self._context(request, intent=evaluation.intent, sensitivity=evaluation.sensitivity)
        if context is None:
            await self._metric("cache_bypass_total")
            return CacheLookupResult(
                decision=CacheDecision(decision=CacheDecisionType.BYPASS, reason="missing_creator_scope"),
                query=query,
                normalized_query=normalized,
                lookup_started_at=started,
            )

        exact_key = build_exact_key(
            normalized_query=normalized,
            context=context.model_dump(mode="json"),
        )
        shadow_candidate: CachedResponsePayload | None = None

        try:
            redis_value = await self.redis.get_exact(exact_key)
        except Exception as exc:
            redis_value = None
            logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                "redis exact cache unavailable; falling back"
            )
        if redis_value is not None:
            payload = self._payload(redis_value)
            if payload is not None:
                if self.mode in {CacheMode.EXACT, CacheMode.SEMANTIC}:
                    await self._metric("cache_hits_total")
                    await self._metric("exact_hits_total")
                    return CacheLookupResult(
                        decision=CacheDecision(
                            decision=CacheDecisionType.HIT,
                            reason="redis_exact_hit",
                            freshness="VALID",
                        ),
                        exact_key=exact_key,
                        query=query,
                        normalized_query=normalized,
                        context=context,
                        response=payload,
                        lookup_started_at=started,
                    )
                shadow_candidate = payload

        try:
            async with self.session_factory() as session:
                repo = CacheRepository(session)
                entry = await repo.exact(exact_key, datetime.now(timezone.utc))
                if entry is not None:
                    payload = self._payload(dict(entry.response_json))
                    if payload is not None:
                        ttl = max(1, int((entry.expires_at - datetime.now(timezone.utc)).total_seconds()))
                        try:
                            await self.redis.set_exact(exact_key, payload.model_dump(mode="json"), ttl)
                        except Exception:
                            pass
                        if self.mode in {CacheMode.EXACT, CacheMode.SEMANTIC}:
                            await repo.record_hit(entry.id)
                            await session.commit()
                            await self._metric("cache_hits_total")
                            await self._metric("exact_hits_total")
                            return CacheLookupResult(
                                decision=CacheDecision(
                                    decision=CacheDecisionType.HIT,
                                    reason="postgres_exact_hit",
                                    cache_entry_id=entry.id,
                                    freshness="VALID",
                                ),
                                exact_key=exact_key,
                                query=query,
                                normalized_query=normalized,
                                context=context,
                                response=payload,
                                lookup_started_at=started,
                            )
                        shadow_candidate = payload
        except Exception as exc:
            logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                "persistent exact lookup failed open"
            )

        embedding: list[float] | None = None
        semantic_candidate: CachedResponsePayload | None = None
        semantic_candidate_id: str | None = None
        semantic_similarity: float | None = None

        if self.mode in {CacheMode.SHADOW, CacheMode.SEMANTIC} and self.embedding_model is not None:
            try:
                embedding = await self.embedding_model.embed(query)
                if embedding:
                    async with self.session_factory() as session:
                        repo = CacheRepository(session)
                        candidates = await repo.semantic_candidates(
                            context=context,
                            embedding=embedding,
                            embedding_model=self.embedding_model_name,
                            embedding_version=self.embedding_version,
                            limit=self.max_candidates,
                            now=datetime.now(timezone.utc),
                        )
                        if candidates:
                            entry, distance = candidates[0]
                            semantic_similarity = max(-1.0, min(1.0, 1.0 - distance))
                            semantic_candidate = self._payload(dict(entry.response_json))
                            semantic_candidate_id = entry.id
                            if semantic_candidate is not None and semantic_similarity >= self.similarity_threshold:
                                if self.mode == CacheMode.SEMANTIC:
                                    await repo.record_hit(entry.id)
                                    await session.commit()
                                    await self._metric("cache_hits_total")
                                    await self._metric("semantic_hits_total")
                                    return CacheLookupResult(
                                        decision=CacheDecision(
                                            decision=CacheDecisionType.HIT,
                                            reason="semantic_context_match",
                                            cache_entry_id=entry.id,
                                            semantic_similarity=semantic_similarity,
                                            freshness="VALID",
                                        ),
                                        exact_key=exact_key,
                                        query=query,
                                        normalized_query=normalized,
                                        context=context,
                                        response=semantic_candidate,
                                        embedding=embedding,
                                        lookup_started_at=started,
                                    )
                                await self._metric("cache_revalidations_total")
                                return CacheLookupResult(
                                    decision=CacheDecision(
                                        decision=CacheDecisionType.REVALIDATE,
                                        reason="shadow_semantic_candidate",
                                        cache_entry_id=entry.id,
                                        semantic_similarity=semantic_similarity,
                                        freshness="VALID",
                                    ),
                                    exact_key=exact_key,
                                    query=query,
                                    normalized_query=normalized,
                                    context=context,
                                    shadow_candidate=semantic_candidate,
                                    shadow_candidate_id=entry.id,
                                    embedding=embedding,
                                    lookup_started_at=started,
                                )
                            if semantic_candidate is not None and semantic_similarity >= self.revalidate_threshold:
                                await self._metric("cache_revalidations_total")
                                return CacheLookupResult(
                                    decision=CacheDecision(
                                        decision=CacheDecisionType.REVALIDATE,
                                        reason="semantic_revalidation_zone",
                                        cache_entry_id=entry.id,
                                        semantic_similarity=semantic_similarity,
                                        freshness="VALID",
                                    ),
                                    exact_key=exact_key,
                                    query=query,
                                    normalized_query=normalized,
                                    context=context,
                                    shadow_candidate=semantic_candidate,
                                    shadow_candidate_id=entry.id,
                                    embedding=embedding,
                                    lookup_started_at=started,
                                )
            except Exception as exc:
                logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                    "semantic lookup failed open"
                )

        lock_token: str | None = None
        if self.mode in {CacheMode.EXACT, CacheMode.SEMANTIC}:
            try:
                lock_token = await self.redis.acquire_lock(exact_key, self.lock_seconds)
                if lock_token is None:
                    peer = await self.redis.wait_for_exact(exact_key, self.singleflight_wait_ms)
                    if peer is not None:
                        peer_payload = self._payload(peer)
                        if peer_payload is not None:
                            await self._metric("cache_hits_total")
                            await self._metric("singleflight_hits_total")
                            return CacheLookupResult(
                                decision=CacheDecision(
                                    decision=CacheDecisionType.HIT,
                                    reason="singleflight_peer_hit",
                                    freshness="VALID",
                                ),
                                exact_key=exact_key,
                                query=query,
                                normalized_query=normalized,
                                context=context,
                                response=peer_payload,
                                embedding=embedding,
                                lookup_started_at=started,
                            )
            except Exception as exc:
                logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                    "single-flight coordination unavailable"
                )

        await self._metric("cache_misses_total")
        logger.bind(
            component="semantic_cache",
            event="CACHE_MISS",
            creator_scope=context.creator_scope,
            intent=context.intent.value,
            lookup_ms=int((time.perf_counter() - started_mono) * 1000),
        ).debug("cache miss")
        return CacheLookupResult(
            decision=CacheDecision(
                decision=CacheDecisionType.MISS,
                reason="no_compatible_cache_entry",
                semantic_similarity=semantic_similarity,
                freshness="VALID",
            ),
            exact_key=exact_key,
            query=query,
            normalized_query=normalized,
            context=context,
            shadow_candidate=shadow_candidate or semantic_candidate,
            shadow_candidate_id=semantic_candidate_id,
            lock_token=lock_token,
            embedding=embedding,
            lookup_started_at=started,
        )

    async def admit(
        self,
        request: InferenceRequest,
        response: InferenceResponse,
        lookup: CacheLookupResult | None,
    ) -> None:
        if lookup is None or lookup.context is None or lookup.exact_key is None or lookup.query is None:
            return
        if lookup.decision.decision == CacheDecisionType.BYPASS:
            return
        if response.metadata.get("capability_intent") is not None or not response.content.strip():
            await self._metric("cache_admission_rejected_total")
            await self.abort(lookup)
            return
        if not evaluate_policy(request, lookup.query).eligible:
            await self._metric("cache_admission_rejected_total")
            await self.abort(lookup)
            return

        embedding = lookup.embedding
        if embedding is None and self.embedding_model is not None:
            try:
                embedding = await self.embedding_model.embed(lookup.query)
            except Exception as exc:
                logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                    "cache admission embedding failed"
                )
        if not embedding:
            await self._metric("cache_admission_rejected_total")
            await self.abort(lookup)
            return

        ttl = ttl_seconds_for_intent(
            lookup.context.intent,
            default_ttl=self.default_ttl_seconds,
            document_ttl=self.document_ttl_seconds,
            deterministic_ttl=self.deterministic_ttl_seconds,
        )
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        payload = self._safe_response(response)
        values = {
            "creator_scope": lookup.context.creator_scope,
            "universe_scope": lookup.context.universe_scope,
            "intent_class": lookup.context.intent.value,
            "sensitivity": lookup.context.sensitivity.value,
            "normalized_query": lookup.normalized_query or normalize_query(lookup.query),
            "exact_key": lookup.exact_key,
            "embedding": embedding,
            "embedding_model": self.embedding_model_name,
            "embedding_version": self.embedding_version,
            "embedding_dimensions": len(embedding),
            "context_hash": lookup.context.context_hash,
            "context_version": lookup.context.context_version,
            "knowledge_version": lookup.context.knowledge_version,
            "retrieval_fingerprint": lookup.context.retrieval_fingerprint,
            "generation_profile_hash": lookup.context.generation_profile_hash,
            "policy_version": lookup.context.policy_version,
            "authorization_fingerprint": lookup.context.authorization_fingerprint,
            "tool_state_class": lookup.context.tool_state_class,
            "response_json": payload.model_dump(mode="json"),
            "validation_status": "VALIDATED",
            "confidence": 1.0,
            "tags": list(lookup.context.tags),
            "expires_at": expires_at,
        }

        async with self.session_factory() as session:
            repo = CacheRepository(session)
            entry = await repo.upsert(values=values)
            await repo.add_event(
                event_type="CACHE_WRITE",
                reason_code="validated_response_admitted",
                creator_scope=lookup.context.creator_scope,
                cache_entry_id=entry.id,
                decision=lookup.decision.decision.value,
                semantic_score=lookup.decision.semantic_similarity,
                metadata={"intent": lookup.context.intent.value, "tags": list(lookup.context.tags)},
            )
            await session.commit()

        try:
            await self.redis.set_exact(lookup.exact_key, payload.model_dump(mode="json"), ttl)
        except Exception as exc:
            logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
                "redis cache write failed open"
            )

        if lookup.shadow_candidate is not None:
            ratio = SequenceMatcher(
                None,
                normalize_query(lookup.shadow_candidate.content),
                normalize_query(response.content),
            ).ratio()
            await self._metric("shadow_candidates_total")
            await self._metric("shadow_matches_total" if ratio >= 0.90 else "shadow_disagreements_total")

        await self._metric("cache_writes_total")
        await self.abort(lookup)

    async def abort(self, lookup: CacheLookupResult | None) -> None:
        if lookup is None or lookup.exact_key is None or lookup.lock_token is None:
            return
        try:
            await self.redis.release_lock(lookup.exact_key, lookup.lock_token)
        except Exception:
            pass

    async def invalidate(
        self,
        *,
        tags: list[str],
        creator_scope: str | None = None,
        reason: str = "event_invalidation",
    ) -> int:
        async with self.session_factory() as session:
            repo = CacheRepository(session)
            keys = await repo.invalidate_tags(tags, creator_scope)
            await repo.add_event(
                event_type="CACHE_INVALIDATE",
                reason_code=reason,
                creator_scope=creator_scope,
                decision=CacheDecisionType.INVALIDATE.value,
                metadata={"tags": tags, "count": len(keys)},
            )
            await session.commit()
        try:
            await self.redis.delete_exact(keys)
        except Exception:
            pass
        if keys:
            await self._metric("cache_invalidations_total", len(keys))
        return len(keys)
