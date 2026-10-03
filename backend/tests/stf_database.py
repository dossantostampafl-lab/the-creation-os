"""A disposable PostgreSQL database for Security Task Force integration tests, behind a guard.

Tests here TRUNCATE tables, so the guard runs before anything else can touch a connection: the URL must come
from STF_TEST_DATABASE_URL (never DATABASE_URL), must not be the application's own database, and its name
must start with `test_stf_`. A refusal happens before any engine, DDL or TRUNCATE exists.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

BACKEND = Path(__file__).resolve().parents[1]
REQUIRED_PREFIX = "test_stf_"

# Everything the tests write, children first. Chronicle and creator rows are theirs to clear as well,
# which is exactly why this may only ever run against a guarded database.
TABLES = (
    "stf_inbox", "stf_outbox", "stf_approvals", "stf_dispatches", "stf_grants", "stf_runs", "stf_contracts",
    "diagnostic_cause_hypotheses", "diagnostic_incidents", "chronicles", "creator",
)


class TestDatabaseRefused(RuntimeError):
    __test__ = False  # not a pytest class, despite the name


def guarded_test_database_url(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    raw = (env.get("STF_TEST_DATABASE_URL") or "").strip()
    if not raw:
        raise TestDatabaseRefused("STF_TEST_DATABASE_URL is required; DATABASE_URL is never used for these tests")
    url = make_url(raw)
    database = url.database or ""
    if not database.startswith(REQUIRED_PREFIX):
        raise TestDatabaseRefused(f"the test database name must start with {REQUIRED_PREFIX!r}, got {database!r}")
    production = (env.get("DATABASE_URL") or "").strip()
    if production:
        other = make_url(production)
        if (other.host, other.port, other.database) == (url.host, url.port, url.database):
            raise TestDatabaseRefused("the test database is the application's database")
    return raw


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": url}, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed: {result.stderr[-600:]}")


def upgrade(url: str, revision: str = "head") -> None:
    _alembic(url, "upgrade", revision)


def downgrade(url: str, revision: str) -> None:
    _alembic(url, "downgrade", revision)


async def truncate(engine: AsyncEngine) -> None:
    """Empty the tables that exist (some may not, before a migration or after a downgrade)."""
    async with engine.begin() as connection:
        present = [
            name for name in TABLES
            if await connection.scalar(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{name}"})
        ]
        if present:
            await connection.execute(text("TRUNCATE " + ", ".join(present) + " RESTART IDENTITY CASCADE"))


@pytest.fixture
async def stf_db():
    """(engine, session_factory) on the guarded database, migrated to head and emptied for this test."""
    try:
        url = guarded_test_database_url()  # first, and before anything can connect
    except TestDatabaseRefused as error:
        if os.environ.get("STF_REQUIRE_TEST_DATABASE") == "1":
            raise
        pytest.skip(str(error))
    upgrade(url)
    engine = create_async_engine(url, pool_size=30, max_overflow=0)
    try:
        await truncate(engine)
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
