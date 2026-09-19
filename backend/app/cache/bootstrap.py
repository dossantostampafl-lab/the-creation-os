from __future__ import annotations

from loguru import logger

from app.ai.embeddings import build_embedding_model
from app.cache.contracts import CacheMode
from app.cache.orchestrator import CacheOrchestrator
from app.cache.redis_store import RedisCacheStore
from app.config import settings
from app.db.session import AsyncSessionLocal

_orchestrator: CacheOrchestrator | None = None


def build_cache_orchestrator() -> CacheOrchestrator | None:
    global _orchestrator
    mode = CacheMode(settings.semantic_cache_mode)
    if mode == CacheMode.OFF:
        return None
    if _orchestrator is not None:
        return _orchestrator

    embedding_model = None
    try:
        embedding_model = build_embedding_model()
    except Exception as exc:
        logger.bind(component="semantic_cache", error_type=exc.__class__.__name__).warning(
            "embedding model unavailable; exact cache remains available"
        )

    _orchestrator = CacheOrchestrator(
        AsyncSessionLocal,
        RedisCacheStore(settings.redis_url, prefix=settings.semantic_cache_redis_prefix),
        embedding_model=embedding_model,
        embedding_model_name=settings.embedding_model,
        embedding_version=settings.semantic_cache_embedding_version,
        mode=mode,
        policy_version=settings.semantic_cache_policy_version,
        similarity_threshold=settings.semantic_cache_similarity_threshold,
        revalidate_threshold=settings.semantic_cache_revalidate_threshold,
        max_candidates=settings.semantic_cache_max_candidates,
        default_ttl_seconds=settings.semantic_cache_ttl_seconds,
        document_ttl_seconds=settings.semantic_cache_document_ttl_seconds,
        deterministic_ttl_seconds=settings.semantic_cache_deterministic_ttl_seconds,
        lock_seconds=settings.semantic_cache_lock_seconds,
        singleflight_wait_ms=settings.semantic_cache_singleflight_wait_ms,
    )
    return _orchestrator
