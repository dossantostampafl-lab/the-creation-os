"""Lote: corrigir bug de migration 0023. The original 0023_universe_agent_seed
used unqualified `ON CONFLICT DO NOTHING`, which matches a conflict on ANY
unique constraint (not just the primary key). universes.code and
capabilities.name each have their own UNIQUE constraint, so a row sharing
one of those values under a different id — e.g. a test fixture inserting
Universe(id=uuid4(), code="knowledge", ...) directly, bypassing this
migration's canonical static ids — made the canonical insert silently
no-op, leaving that id absent, and the agents insert two loops later (its
universe_id FK referencing that now-missing id) then failed with a
confusing FK violation instead of a clear error at the real point of
conflict.

Reproduced in isolation before writing the fix: a *pure* migration round
trip (upgrade head from empty, downgrade to 0022, upgrade head again, no
test fixtures touching the database) never reproduced this — it only
manifests once something outside the migration framework has already
inserted a same-code/name row under a non-canonical id. Fixed by
qualifying every ON CONFLICT with its real target column(s).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from db_safety import create_isolated_test_engine, validated_test_database_url
from sqlalchemy import text

from app.db.alembic_utils import resolve_alembic_head

pytestmark = pytest.mark.integration


def run_alembic(revision: str, operation: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = validated_test_database_url()
    subprocess.run(
        [sys.executable, "-m", "alembic", operation, revision],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_0023_pure_round_trip_from_intermediate_revision_succeeds():
    """The scenario the bug report was originally about: resuming `alembic
    upgrade head` after a downgrade that lands below 0023 — no contamination
    involved. Regression guard: this must keep succeeding."""
    run_alembic("0022_pgvector_extension", "downgrade")
    run_alembic("head", "upgrade")

    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        # Resolved dynamically, not hardcoded — a fixed string here goes
        # stale the next time a migration is added after this one (see
        # ARCHITECTURE.md, Lote: corrigir revisão stale em
        # test_migration_0023_seed_idempotency.py e test_auth.py).
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == resolve_alembic_head()
        assert await connection.scalar(
            text("SELECT count(*) FROM universes WHERE id = '10000000-0000-0000-0000-000000000001'")
        ) == 1
        assert await connection.scalar(
            text("SELECT count(*) FROM agents WHERE id = '30000000-0000-0000-0000-000000000001'")
        ) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_0023_conflicting_row_under_different_id_now_fails_loudly_not_confusingly():
    """The actual bug's real trigger: something outside this migration (a
    stray test fixture, most realistically) has already inserted a
    same-code Universe row under a non-canonical id. Before the fix this
    surfaced as a bewildering FK violation on `agents_universe_id_fkey`
    two loops away from the real cause. After the fix it must fail
    immediately with a UniqueViolation naming the actual conflicting
    constraint (`universes_code_key`) — a real, clear signal instead of a
    silently-swallowed conflict. This is *not* a "now it succeeds" case —
    genuinely conflicting data should keep failing; only the clarity and
    immediacy of the failure improves."""
    run_alembic("0022_pgvector_extension", "downgrade")

    engine = create_isolated_test_engine()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO universes (id, code, name, active) "
                "VALUES ('99999999-0000-0000-0000-000000000099', 'knowledge', 'Conhecimento', true)"
            )
        )
    await engine.dispose()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": validated_test_database_url()},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "universes_code_key" in result.stderr
    assert "agents_universe_id_fkey" not in result.stderr

    # Clean up the contamination and the now-partial migration state so
    # later tests in the same session are unaffected.
    run_alembic("0022_pgvector_extension", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM universes WHERE id = '99999999-0000-0000-0000-000000000099'")
        )
    await engine.dispose()
    run_alembic("head", "upgrade")
