from __future__ import annotations

from pydantic import BaseModel, Field

from app.cache.contracts import CacheMode
from app.cache.redis_store import RedisCacheStore
from app.cache.repository import CacheRepository
from app.config import settings
from app.db.session import AsyncSessionLocal


class CacheStatusSnapshot(BaseModel):
    mode: CacheMode
    policy_version: str
    embedding_model: str
    persistent_entries: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, int] = Field(default_factory=dict)
    redis_available: bool
    postgres_available: bool


async def configured_cache_status() -> CacheStatusSnapshot:
    metrics: dict[str, int] = {}
    redis_available = True
    store = RedisCacheStore(settings.redis_url, prefix=settings.semantic_cache_redis_prefix)
    try:
        metrics = await store.metrics_snapshot()
    except Exception:
        redis_available = False
    finally:
        try:
            await store.close()
        except Exception:
            pass

    counts: dict[str, int] = {}
    postgres_available = True
    try:
        async with AsyncSessionLocal() as session:
            counts = await CacheRepository(session).counts()
    except Exception:
        postgres_available = False

    return CacheStatusSnapshot(
        mode=CacheMode(settings.semantic_cache_mode),
        policy_version=settings.semantic_cache_policy_version,
        embedding_model=settings.embedding_model,
        persistent_entries=counts,
        metrics=metrics,
        redis_available=redis_available,
        postgres_available=postgres_available,
    )
