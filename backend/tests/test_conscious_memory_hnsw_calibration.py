"""Lote: calibração de parâmetros HNSW para volume de produção real
(conscious_memory). The ix_conscious_memory_embedding_hnsw index
(migration 0026) was built with pgvector's defaults (m=16,
ef_construction=64), measured only against a 2000-row synthetic
benchmark (test_conscious_memory_ann_performance.py) at the time. This
file investigates whether those defaults hold at volumes well above
that — 5k/20k/100k rows — with real measurements: index build time,
search latency, and approximate-search recall against an exact
(index-disabled) baseline. Reuses that lote's exact embedding generator
(_embedding, imported below) — not a new one.

Marked "benchmark" (separate from "integration"/"concurrency"): these
tests generate tens of thousands of rows and build a real HNSW index
from scratch per volume — genuinely slow (minutes, not seconds), meant
to be run deliberately when re-calibration is warranted, not on every
lote. Exclude with -m "not benchmark". See ARCHITECTURE.md, Lote:
Calibração de parâmetros HNSW, for the real numbers this produced and
the decision made from them.
"""

from __future__ import annotations

import time
import uuid

import pytest
from db_safety import create_isolated_test_engine
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_conscious_memory_ann_performance import _embedding

from app.models.entities import ConsciousMemory
from app.repositories.conscious_memory import ConsciousMemoryRepository

pytestmark = [pytest.mark.integration, pytest.mark.benchmark]

INSERT_BATCH_SIZE = 5000
SEARCH_QUERIES = 10
SEARCH_CALLS_PER_QUERY = 10
RECALL_SAMPLE_QUERIES = 20
RECALL_K = 10


async def _populate(factory, row_count: int) -> None:
    async with factory() as session:
        for batch_start in range(0, row_count, INSERT_BATCH_SIZE):
            batch = [
                {
                    "id": str(uuid.uuid4()),
                    "source_type": "benchmark",
                    "source_id": str(i),
                    "content": f"synthetic memory {i}",
                    "metadata_json": {},
                    "embedding": _embedding(i),
                }
                for i in range(batch_start, min(batch_start + INSERT_BATCH_SIZE, row_count))
            ]
            await session.execute(insert(ConsciousMemory), batch)
        await session.commit()


async def _build_index(engine, *, m: int, ef_construction: int) -> float:
    async with engine.begin() as connection:
        await connection.execute(text("DROP INDEX IF EXISTS ix_conscious_memory_embedding_hnsw"))
        start = time.perf_counter()
        await connection.execute(
            text(
                "CREATE INDEX ix_conscious_memory_embedding_hnsw ON conscious_memory "
                f"USING hnsw (embedding vector_cosine_ops) WITH (m = {m}, ef_construction = {ef_construction})"
            )
        )
        build_seconds = time.perf_counter() - start
        # Same reason as test_conscious_memory_ann_performance.py's fixture:
        # a freshly bulk-inserted/reindexed table has no fresh statistics
        # yet, and the planner would underestimate row count without this.
        await connection.execute(text("ANALYZE conscious_memory"))
    return build_seconds


async def _measure_search_latency(factory, query_embeddings: list[list[float]], *, limit: int = 5) -> float:
    async with factory() as session:
        repository = ConsciousMemoryRepository(session)
        await repository.search_by_embedding(query_embeddings[0], limit=limit)  # warm connection/plan cache
        start = time.perf_counter()
        calls = 0
        for embedding in query_embeddings:
            for _ in range(SEARCH_CALLS_PER_QUERY):
                await repository.search_by_embedding(embedding, limit=limit)
                calls += 1
        return (time.perf_counter() - start) / calls


async def _exact_top_k(factory, embedding: list[float], k: int) -> set[str]:
    """The true top-k under the exact same cosine_distance operator HNSW
    approximates — the `<=>` operator itself is always exact; only *which*
    candidates the index examines is approximate. Disabling index/bitmap
    scans for this session forces a Seq Scan, i.e. brute force over every
    row, giving a real ground truth to compare HNSW's result against."""
    query_literal = "[" + ",".join(str(v) for v in embedding) + "]"
    async with factory() as session:
        await session.execute(text("SET LOCAL enable_indexscan = off"))
        await session.execute(text("SET LOCAL enable_bitmapscan = off"))
        result = await session.execute(
            text(f"SELECT id FROM conscious_memory ORDER BY embedding <=> '{query_literal}'::vector LIMIT {k}")
        )
        return {row[0] for row in result.all()}


async def _measure_recall(factory, query_embeddings: list[list[float]], *, k: int) -> float:
    overlaps = []
    async with factory() as session:
        repository = ConsciousMemoryRepository(session)
        for embedding in query_embeddings:
            approx_ids = {item.id for item in await repository.search_by_embedding(embedding, limit=k)}
            exact_ids = await _exact_top_k(factory, embedding, k)
            overlaps.append(len(approx_ids & exact_ids) / k)
    return sum(overlaps) / len(overlaps)


async def run_benchmark(row_count: int, *, m: int = 16, ef_construction: int = 64) -> dict:
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE conscious_memory RESTART IDENTITY CASCADE"))

        populate_start = time.perf_counter()
        await _populate(factory, row_count)
        populate_seconds = time.perf_counter() - populate_start

        build_seconds = await _build_index(engine, m=m, ef_construction=ef_construction)

        # Query embeddings deterministic but outside the inserted id range
        # (row_count + i), so a query never trivially matches its own
        # inserted row at cosine distance zero.
        query_embeddings = [_embedding(row_count + i) for i in range(max(SEARCH_QUERIES, RECALL_SAMPLE_QUERIES))]
        latency_seconds = await _measure_search_latency(factory, query_embeddings[:SEARCH_QUERIES])
        recall = await _measure_recall(factory, query_embeddings[:RECALL_SAMPLE_QUERIES], k=RECALL_K)

        result = {
            "row_count": row_count,
            "m": m,
            "ef_construction": ef_construction,
            "populate_seconds": populate_seconds,
            "build_seconds": build_seconds,
            "latency_ms": latency_seconds * 1000,
            "recall_at_10": recall,
        }
        print(
            f"\n[HNSW m={m} ef_construction={ef_construction}] rows={row_count}: "
            f"populate={populate_seconds:.2f}s build={build_seconds:.2f}s "
            f"latency={result['latency_ms']:.2f}ms/call recall@{RECALL_K}={recall:.3f}"
        )
        return result
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("row_count", [5000, 20000, 100000])
async def test_hnsw_default_params_at_volume(row_count):
    """Current production index parameters (m=16, ef_construction=64,
    the pgvector defaults migration 0026 used) at volumes 2.5x/10x/50x
    above the 2000-row benchmark this project has measured so far."""
    result = await run_benchmark(row_count)
    # A sanity floor, not a tuning target: recall collapsing this low would
    # mean something is actually broken (wrong operator, missing index),
    # not just "could be calibrated better". The real pass/fail judgment
    # for calibration purposes is made from the printed numbers, in
    # ARCHITECTURE.md, not by this assertion.
    assert result["recall_at_10"] >= 0.5, result
