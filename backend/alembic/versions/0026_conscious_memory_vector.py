"""Convert conscious_memory.embedding to a native pgvector column + HNSW index.

Revision ID: 0026_conscious_memory_vector
Revises: 0025_god_system_query
Create Date: 2026-08-01 00:00:00.000000

Lote 2.5 stored `embedding` as a plain Postgres `real[]` array (see
MIGRATIONS.md / app/models/entities.py) — the `vector` extension was
enabled (0022_pgvector_extension) but never actually wired to a real
`vector` column, so search was a bounded in-Python cosine ranking over up
to 500 candidates, not a real ANN query (see app/repositories/conscious_memory.py's
prior docstring and ARCHITECTURE.md's Lote 2.5 entry).

Confirmed before writing this migration: zero rows in `conscious_memory`
in the real persistent database (`SELECT count(*) FROM conscious_memory`
= 0) — no data conversion ETL needed, only a schema change. `real[]` casts
directly to `vector(N)` in pgvector (`ARRAY[1,2,3]::real[]::vector`
verified to work), so `USING embedding::vector(8)` is safe even if a row
existed.

Dimension is hardcoded to 8, matching `settings.conscious_memory_embedding_dim`'s
configured default (app/config.py, CONSCIOUS_MEMORY_EMBEDDING_DIM). Unlike
real[]/JSON, `vector(N)`'s dimension is fixed at the column-DDL level —
changing the configured embedding dimension in the future requires a
follow-up migration to also ALTER this column's dimension. Documented as
a real, inherent constraint in ARCHITECTURE.md, not a gap.

Index: HNSW, not IVFFlat. Confirmed the installed pgvector extension is
0.8.5 (`SELECT extversion FROM pg_extension WHERE extname='vector'`) —
HNSW has been supported and stable since pgvector 0.5.0, so it is
available and is pgvector's own recommended default for most workloads:
unlike IVFFlat, HNSW needs no `lists` parameter calibrated to expected
row count, builds incrementally (no degenerate clustering on an empty or
small table), and needs no periodic REINDEX as the table grows. Default
build parameters (`m=16, ef_construction=64`) are used — the pgvector
defaults, appropriate for this table's expected low-thousands row scale;
see ARCHITECTURE.md for the tuning-later note.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_conscious_memory_vector"
down_revision: str | None = "0025_god_system_query"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 8


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE conscious_memory "
        f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) USING embedding::vector({EMBEDDING_DIM})"
    )
    op.execute(
        "CREATE INDEX ix_conscious_memory_embedding_hnsw ON conscious_memory "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_conscious_memory_embedding_hnsw")
    op.execute(
        "ALTER TABLE conscious_memory "
        "ALTER COLUMN embedding TYPE real[] USING embedding::real[]"
    )
