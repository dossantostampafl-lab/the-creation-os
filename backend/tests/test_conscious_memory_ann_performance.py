"""Lote: busca ANN real via pgvector. Proves the migration away from the
Lote 2.5 in-Python cosine scan (bounded to 500 candidates) to a native
pgvector HNSW index actually changed what runs: the index is used (EXPLAIN),
and it is measurably faster than the old approach at a volume well above
the old 500-candidate cap — real numbers, not a theoretical claim.
"""

from __future__ import annotations

import random
import time
import uuid

import pytest
from db_safety import create_isolated_test_engine
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.entities import ConsciousMemory
from app.repositories.conscious_memory import ConsciousMemoryRepository

pytestmark = pytest.mark.integration

ROW_COUNT = 2000  # well above the old all_candidates() cap of 500
DIM = 8


def _embedding(i: int) -> list[float]:
    # Deterministic (seeded) but non-parallel 8-dim vectors — cosine
    # similarity is scale-invariant, so a naive modulo-based generator
    # produces many rows that are exact positive scalar multiples of each
    # other (indistinguishable to cosine distance); a seeded PRNG avoids
    # that collision while staying fully reproducible per row index.
    return [random.Random(i * DIM + j).uniform(0.01, 1.0) for j in range(DIM)]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """The exact formula app.repositories.conscious_memory.cosine_similarity()
    used before this lote removed it — reconstructed here only to measure
    the old approach's real timing for comparison, not as production code."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@pytest.fixture
async def large_conscious_memory_db():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE conscious_memory RESTART IDENTITY CASCADE"))
    async with factory() as session:
        rows = [
            {
                "id": str(uuid.uuid4()),
                "source_type": "test",
                "source_id": str(i),
                "content": f"synthetic memory {i}",
                "metadata_json": {},
                "embedding": _embedding(i),
            }
            for i in range(ROW_COUNT)
        ]
        await session.execute(insert(ConsciousMemory), rows)
        await session.commit()
    async with engine.begin() as connection:
        # A freshly bulk-inserted table has no statistics yet — autovacuum
        # would eventually ANALYZE it, but not synchronously within this
        # test. Without this, the planner underestimates the row count and
        # picks a Seq Scan instead of the HNSW index (confirmed by hand
        # before adding this: identical query, Seq Scan pre-ANALYZE,
        # Index Scan using ix_conscious_memory_embedding_hnsw post-ANALYZE).
        await connection.execute(text("ANALYZE conscious_memory"))
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_hnsw_index_is_actually_used_not_a_sequential_scan(large_conscious_memory_db):
    factory = large_conscious_memory_db
    async with factory() as session:
        query_literal = "[" + ",".join(str(v) for v in _embedding(0)) + "]"
        explain = await session.execute(
            text(
                "EXPLAIN SELECT id FROM conscious_memory "
                f"ORDER BY embedding <=> '{query_literal}'::vector LIMIT 5"
            )
        )
        plan = "\n".join(row[0] for row in explain.all())
    assert "ix_conscious_memory_embedding_hnsw" in plan, plan
    assert "Index Scan" in plan, plan
    assert "Seq Scan" not in plan, plan


@pytest.mark.asyncio
async def test_pgvector_search_finds_the_real_nearest_neighbor_at_scale(large_conscious_memory_db):
    factory = large_conscious_memory_db
    async with factory() as session:
        repository = ConsciousMemoryRepository(session)
        query_embedding = _embedding(42)
        results = await repository.search_by_embedding(query_embedding, limit=5)
    assert results[0].source_id == "42"  # the exact row the query embedding was built from


@pytest.mark.asyncio
async def test_pgvector_search_is_measurably_faster_than_the_old_in_python_scan(large_conscious_memory_db):
    """Real, measured comparison at ROW_COUNT (2000) rows — well above the
    old all_candidates(500) cap. The old approach's cost was dominated by
    transferring up to 500 full rows (content/metadata/embedding) over the
    network and ranking them in Python; the new approach transfers only
    the LIMIT rows already ranked by the index."""
    factory = large_conscious_memory_db
    query_embedding = _embedding(7)

    async with factory() as session:
        repository = ConsciousMemoryRepository(session)
        # warm connection/plan cache before timing
        await repository.search_by_embedding(query_embedding, limit=5)
        start = time.perf_counter()
        for _ in range(10):
            await repository.search_by_embedding(query_embedding, limit=5)
        pgvector_seconds = (time.perf_counter() - start) / 10

    async with factory() as session:
        repository = ConsciousMemoryRepository(session)
        candidates = await repository.all_candidates(limit=500)  # the old cap
        start = time.perf_counter()
        for _ in range(10):
            candidates = await repository.all_candidates(limit=500)
            ranked = sorted(
                candidates, key=lambda item: _cosine_similarity(query_embedding, list(item.embedding)), reverse=True
            )
            ranked[:5]
        python_seconds = (time.perf_counter() - start) / 10

    print(f"\npgvector (HNSW, {ROW_COUNT} rows, LIMIT 5): {pgvector_seconds * 1000:.2f}ms/call")
    print(f"in-Python (old, 500-row fetch + Python rank): {python_seconds * 1000:.2f}ms/call")
    print(f"speedup: {python_seconds / pgvector_seconds:.1f}x")

    assert pgvector_seconds < python_seconds
