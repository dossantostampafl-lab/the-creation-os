"""Lote: health check com revisão Alembic dinâmica. Proves /health/ready no
longer depends on a hand-maintained EXPECTED_ALEMBIC_REVISION string — the
exact bug that left it returning 503 permanently, unnoticed, across two
prior lotes (SYSTEM_QUERY, pgvector) each adding a migration without
anyone remembering to bump that constant.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from db_safety import create_isolated_test_engine, validated_test_database_url
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.health import resolve_alembic_head
from app.config import settings
from app.db.session import get_session
from app.main import app

pytestmark = pytest.mark.integration

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_VERSIONS_DIR = _BACKEND_ROOT / "alembic" / "versions"


def auth() -> dict[str, str]:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def run_alembic(revision: str, operation: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = validated_test_database_url()
    subprocess.run(
        [sys.executable, "-m", "alembic", operation, revision],
        cwd=_BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def health_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


def test_no_hardcoded_revision_string_remains():
    """The whole point of this lote: app/api/health.py must not import or
    define any literal Alembic revision id. resolve_alembic_head() derives
    it from the migration scripts on disk every call."""
    import app.api.health as health_module

    assert not hasattr(health_module, "EXPECTED_ALEMBIC_REVISION")
    assert resolve_alembic_head() == resolve_alembic_head()  # deterministic, callable repeatedly


@pytest.mark.asyncio
async def test_health_ready_reports_healthy_at_the_real_migration_head(health_database):
    real_head = resolve_alembic_head()  # same mechanism the test resolves against — no hardcoded string here either
    async with health_database() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == real_head

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready", headers=auth())
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_health_ready_migration_round_trip_reports_unhealthy_behind_head(health_database):
    """Named with "migration_round_trip" so conftest.py's guard hooks clean
    up the seed/evolving-constraint tables before and after, and restore
    the database to head afterward — same convention test_god_integration.py
    and friends already use."""
    real_head = resolve_alembic_head()
    run_alembic("0025_god_system_query", "downgrade")  # one revision behind head
    try:
        async with health_database() as session:
            behind_revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        assert behind_revision != real_head

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready", headers=auth())
        assert response.status_code == 503
    finally:
        run_alembic("head", "upgrade")


@pytest.mark.asyncio
async def test_health_ready_migration_round_trip_tracks_a_new_migration_automatically(health_database):
    """The actual regression test: add a real migration file after the
    current head, confirm resolve_alembic_head() picks it up with zero
    changes to app/api/health.py, confirm /health/ready correctly demands
    it once present, and confirm applying it via `alembic upgrade head`
    (not touching health.py at all) makes the endpoint healthy again."""
    original_head = resolve_alembic_head()
    # alembic_version.version_num is varchar(32) — must fit within that.
    temp_revision = "zzzz_health_regr_tmp"
    temp_file = _VERSIONS_DIR / f"{temp_revision}.py"
    temp_file.write_text(
        f'''"""Temporary migration created only by
tests/test_health.py::test_health_ready_migration_round_trip_tracks_a_new_migration_automatically
— deleted by that test's own cleanup. If you see this file outside a test
run, delete it; it is not a real migration.
"""
from __future__ import annotations

revision = "{temp_revision}"
down_revision = "{original_head}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
''',
        encoding="utf-8",
    )
    try:
        # Adding the file alone (nothing applied to any database yet)
        # already changes what resolve_alembic_head() reports — proves the
        # mechanism reads the migration scripts, not a remembered constant.
        assert resolve_alembic_head() == temp_revision
        assert resolve_alembic_head() != original_head

        # The real database is still at the old head, one revision behind
        # this newly-discovered one — /health/ready must now correctly
        # report unhealthy, with no code change of any kind.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready", headers=auth())
        assert response.status_code == 503

        # Apply the migration for real — still zero changes to health.py.
        run_alembic("head", "upgrade")
        async with health_database() as session:
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == temp_revision

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready", headers=auth())
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
    finally:
        run_alembic(original_head, "downgrade")
        temp_file.unlink(missing_ok=True)
        assert resolve_alembic_head() == original_head
        run_alembic("head", "upgrade")
