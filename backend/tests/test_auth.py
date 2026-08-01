from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from db_safety import create_isolated_test_engine, validated_test_database_url
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import app

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


@pytest.fixture
async def empty_creator_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE creator RESTART IDENTITY CASCADE"))

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides.clear()
    from app.db.session import get_session

    app.dependency_overrides[get_session] = override_session
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_0024_migration_round_trip_singleton_constraint():
    run_alembic("0024_creator_singleton", "upgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024_creator_singleton"
        constraints = set(
            (await connection.scalars(text("SELECT conname FROM pg_constraint WHERE conrelid='creator'::regclass"))).all()
        )
        assert constraints >= {"uq_creator_singleton", "ck_creator_singleton_true"}
    await engine.dispose()

    run_alembic("0023_universe_agent_seed", "downgrade")
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0023_universe_agent_seed"
        constraints = set(
            (await connection.scalars(text("SELECT conname FROM pg_constraint WHERE conrelid='creator'::regclass"))).all()
        )
        assert "uq_creator_singleton" not in constraints
        assert "ck_creator_singleton_true" not in constraints
    await engine.dispose()
    run_alembic("0024_creator_singleton", "upgrade")


@pytest.mark.asyncio
async def test_bootstrap_rejects_second_creator_sequential(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "first-password"}
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/v1/auth/bootstrap", json={"username": "creator-two", "password": "second-password"}
        )
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_rejects_second_creator_concurrent(empty_creator_database):
    """Reproduces the race the check-then-insert pattern alone cannot close.

    Two different usernames on purpose: the pre-fix code only had a UNIQUE
    constraint on `username`, so two concurrent requests with *different*
    usernames could both succeed and create two Creators before migration
    0024_creator_singleton added `uq_creator_singleton`. This must fail
    with exactly one 201 and one 409, and exactly one row in `creator`.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            client.post("/api/v1/auth/bootstrap", json={"username": "creator-a", "password": "password-a"}),
            client.post("/api/v1/auth/bootstrap", json={"username": "creator-b", "password": "password-b"}),
        )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409]

    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM creator")) == 1
    await engine.dispose()
