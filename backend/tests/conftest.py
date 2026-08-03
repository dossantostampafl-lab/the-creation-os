from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from db_safety import UnsafeTestDatabaseConfiguration, validated_test_database_url

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-at-least-32-characters")
os.environ.setdefault("CREATOR_BOOTSTRAP_USERNAME", "creator")
os.environ.setdefault("CREATOR_BOOTSTRAP_PASSWORD", "test-password")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Lote: investigação de fragilidade de ordenação em test_god_integration.py.
# Root cause (confirmed by reproduction, see ARCHITECTURE.md), two related
# manifestations of the same pattern:
#
# (a) Many integration fixtures across this suite (e.g. knowledge_memory_db
#     in test_knowledge_memory_integration.py) legitimately TRUNCATE and
#     reseed universes/capabilities/agents with their own synthetic ids for
#     their own isolation. Those rows share the same `code`/`name` as
#     migration 0023_universe_agent_seed's canonical static-id seed data
#     (e.g. capability name "knowledge_research"), and are never restored
#     afterward. When a *later* "migration round trip" test's teardown
#     re-runs `alembic upgrade head`, 0023's seed insert hits a real
#     UniqueViolation on that shared name/code under a different id —
#     correctly loud since the Lote: corrigir bug de migration 0023 fix
#     (qualified `ON CONFLICT (id) DO NOTHING`) — so the recovery fails.
# (b) Symmetrically, other tests' `god_database`-style fixtures write real
#     rows with `interaction_type='SYSTEM_QUERY'` into
#     god_conversation_interactions. When a round-trip test's *own* body
#     downgrades through 0025_god_system_query, that migration's downgrade()
#     re-adds the OLDER, narrower CHECK constraint (without SYSTEM_QUERY) —
#     which the leftover SYSTEM_QUERY row now violates, failing the ALTER
#     TABLE itself with a CheckViolationError, mid-test, before any teardown
#     even runs.
#
# In both cases: a round-trip test downgrades through a migration that
# added/loosened a constraint, and whatever unrelated data another test
# left behind no longer satisfies the OLDER schema being restored. Fix:
# TRUNCATE both the migration-managed seed tables and the "evolving
# constraint" application tables immediately before *and* after every
# migration_round_trip test — before, so the test's own downgrade never
# meets incompatible leftover data; after, so 0023's reseed always starts
# from guaranteed-empty tables regardless of what the test itself did. This
# is the one convergence point for every test file that touches these
# tables (many do), so it fixes the systemic pattern here rather than
# patching each fixture or each round-trip test individually.
_MIGRATION_SEED_TABLES = "agent_capabilities, agents, capabilities, universes"
_EVOLVING_CONSTRAINT_TABLES = "god_conversation_interactions, sophia_understandings, rockmam_possibility_assessments"
_ROUND_TRIP_GUARD_TABLES = f"{_MIGRATION_SEED_TABLES}, {_EVOLVING_CONSTRAINT_TABLES}"


def _clear_round_trip_guard_tables(test_database_url: str) -> None:
    # On a genuinely fresh database (no migration ever applied — e.g. the
    # very first call of the session-scoped fixture below) these tables
    # don't exist yet; nothing to clear, `alembic upgrade head` creates
    # them from scratch.
    sync_url = test_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    with psycopg.connect(sync_url, autocommit=True) as connection:
        try:
            connection.execute(f"TRUNCATE {_ROUND_TRIP_GUARD_TABLES} RESTART IDENTITY CASCADE")
        except psycopg.errors.UndefinedTable:
            pass


def _restore_to_head(test_database_url: str) -> None:
    _clear_round_trip_guard_tables(test_database_url)
    environment = os.environ.copy()
    environment["DATABASE_URL"] = test_database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_database_to_head():
    """Guarantee the disposable test database starts at Alembic head.

    Without this, a freshly created TEST_DATABASE_URL has no alembic_version
    row, and test_0009_migration_round_trip's `alembic downgrade` has no
    valid current revision to downgrade from — it fails immediately,
    regardless of platform. This mirrors the per-test restore already done
    in pytest_runtest_teardown below, just once, before the session starts.
    """
    try:
        test_database_url = validated_test_database_url()
    except UnsafeTestDatabaseConfiguration:
        return
    _restore_to_head(test_database_url)


def pytest_runtest_setup(item):
    """Guards manifestation (b) above: clear tables that could hold data
    incompatible with an older schema *before* a round-trip test's own body
    runs its downgrade, not just after."""
    if "migration_round_trip" not in item.name:
        return
    try:
        test_database_url = validated_test_database_url()
    except UnsafeTestDatabaseConfiguration:
        return
    _clear_round_trip_guard_tables(test_database_url)


def pytest_runtest_teardown(item, nextitem):
    if "migration_round_trip" not in item.name:
        return
    try:
        test_database_url = validated_test_database_url()
    except UnsafeTestDatabaseConfiguration:
        return
    _restore_to_head(test_database_url)
