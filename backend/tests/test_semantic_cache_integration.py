from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cache.contracts import CacheDecisionType, CacheMode
from app.cache.orchestrator import CacheOrchestrator
from app.cache.redis_store import RedisCacheStore
from app.inference.contracts import InferenceRequest, InferenceResponse, ModelRequirements
from app.models.cache import CacheEvent, SemanticCacheEntry

pytestmark = pytest.mark.integration


class EquivalentEmbedding:
    async def embed(self, text: str) -> list[float]:
        if "central core" in text.lower():
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]


def request(query: str, creator: str = "creator-a", **metadata) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "system", "content": "stable-system-v1"}, {"role": "user", "content": query}],
        model="model-a",
        requirements=ModelRequirements(preferred_provider="provider-a"),
        metadata={
            "creator_id": creator,
            "cache_intent": "EXPLANATION",
            "cache_sensitivity": "PRIVATE",
            "generation_contract_version": "v1",
            "cache_tags": ["knowledge:central-core"],
            **metadata,
        },
    )


@pytest.fixture
async def cache_runtime():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(delete(CacheEvent))
        await session.execute(delete(SemanticCacheEntry))
        await session.commit()

    redis_store = RedisCacheStore(
        os.environ["REDIS_URL"],
        prefix=f"test:semantic-cache:{uuid.uuid4().hex}",
    )
    orchestrator = CacheOrchestrator(
        sessions,
        redis_store,
        embedding_model=EquivalentEmbedding(),
        embedding_model_name="test-embedding",
        embedding_version="v1",
        mode=CacheMode.SEMANTIC,
        policy_version="test-v1",
        similarity_threshold=0.94,
        revalidate_threshold=0.90,
        max_candidates=5,
        default_ttl_seconds=600,
        document_ttl_seconds=300,
        deterministic_ttl_seconds=600,
        lock_seconds=5,
        singleflight_wait_ms=50,
    )
    yield orchestrator
    await redis_store.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_exact_and_semantic_hits_are_creator_scoped(cache_runtime: CacheOrchestrator) -> None:
    first = request("Explain the Central Core")
    first_lookup = await cache_runtime.lookup(first)
    assert first_lookup.decision.decision is CacheDecisionType.MISS
    await cache_runtime.admit(
        first,
        InferenceResponse(provider="provider-a", model="model-a", content="Central Core answer"),
        first_lookup,
    )

    exact = await cache_runtime.lookup(first)
    assert exact.decision.decision is CacheDecisionType.HIT
    assert exact.response is not None and exact.response.content == "Central Core answer"

    semantic = await cache_runtime.lookup(request("Describe how the Central Core works"))
    assert semantic.decision.decision is CacheDecisionType.HIT
    assert semantic.decision.semantic_similarity is not None
    assert semantic.decision.semantic_similarity >= 0.94

    other_creator = await cache_runtime.lookup(request("Describe how the Central Core works", creator="creator-b"))
    assert other_creator.decision.decision is CacheDecisionType.MISS
    await cache_runtime.abort(other_creator)


@pytest.mark.asyncio
async def test_live_and_action_queries_bypass_even_in_semantic_mode(cache_runtime: CacheOrchestrator) -> None:
    live = await cache_runtime.lookup(
        request("What is the current system status now?", cache_intent="LIVE_STATE")
    )
    action = await cache_runtime.lookup(
        request("Activate the agent", cache_intent="SYSTEM_COMMAND", cache_policy="bypass")
    )
    assert live.decision.decision is CacheDecisionType.BYPASS
    assert action.decision.decision is CacheDecisionType.BYPASS


@pytest.mark.asyncio
async def test_tag_invalidation_removes_redis_and_database_hit(cache_runtime: CacheOrchestrator) -> None:
    req = request("Explain the Central Core")
    lookup = await cache_runtime.lookup(req)
    await cache_runtime.admit(
        req,
        InferenceResponse(provider="provider-a", model="model-a", content="Central Core answer"),
        lookup,
    )
    assert (await cache_runtime.lookup(req)).decision.decision is CacheDecisionType.HIT

    invalidated = await cache_runtime.invalidate(
        tags=["knowledge:central-core"],
        creator_scope="creator-a",
        reason="knowledge_updated",
    )
    assert invalidated == 1
    after = await cache_runtime.lookup(req)
    assert after.decision.decision is CacheDecisionType.MISS
    await cache_runtime.abort(after)


@pytest.mark.asyncio
async def test_shared_exact_entry_stays_invalidatable_by_every_conversation(cache_runtime: CacheOrchestrator) -> None:
    # Two conversations miss concurrently on the same question and both admit an answer.
    first = request("Explain the Central Core", cache_tags=["conversation:a"])
    second = request("Explain the Central Core", cache_tags=["conversation:b"])
    first_lookup = await cache_runtime.lookup(first)
    second_lookup = await cache_runtime.lookup(second)
    assert first_lookup.exact_key == second_lookup.exact_key
    answer = InferenceResponse(provider="provider-a", model="model-a", content="The Central Core is shared.")
    await cache_runtime.admit(first, answer, first_lookup)
    await cache_runtime.admit(second, answer, second_lookup)

    assert await cache_runtime.invalidate(tags=["conversation:a"], creator_scope="creator-a") == 1
    third = await cache_runtime.lookup(request("Explain the Central Core", cache_tags=["conversation:c"]))
    assert third.decision.decision != CacheDecisionType.HIT
