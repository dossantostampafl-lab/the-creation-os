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
    # The migration_round_trip guard (conftest.py) only restores to *head*
    # between tests, never to 0024 specifically — and 0024 stopped being
    # head once 0025/0026 were added. Downgrading below 0024 first, rather
    # than assuming we already start there, makes this test correct
    # regardless of how many later migrations exist (see ARCHITECTURE.md,
    # Lote: corrigir revisão stale em test_migration_0023_seed_idempotency.py
    # e test_auth.py).
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
    engine = create_isolated_test_engine()
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024_creator_singleton"
        constraints = set(
            (await connection.scalars(text("SELECT conname FROM pg_constraint WHERE conrelid='creator'::regclass"))).all()
        )
        assert constraints >= {"uq_creator_singleton", "ck_creator_singleton_true"}
    await engine.dispose()


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
async def test_login_succeeds_with_valid_credentials_and_returns_tokens(empty_creator_database):
    """Auditoria: seção 3 (autenticação). Comportamento já correto em
    app/services/auth.py / app/auth/routes.py — só nunca tinha teste."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})

        response = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] and body["refresh_token"]
        assert body["access_token"] != body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_rejects_wrong_username_and_wrong_password_identically(empty_creator_database):
    """Credential-enumeration guard: a wrong username and a wrong password
    for a real username must be indistinguishable to the caller — same
    status code, same detail message. Confirms AuthService.login()'s
    single `creator is None or not verify_password(...)` branch actually
    behaves that way over the real HTTP surface, not just by code reading."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})

        wrong_username = await client.post(
            "/api/v1/auth/login", json={"username": "does-not-exist", "password": "correct-password"}
        )
        wrong_password = await client.post(
            "/api/v1/auth/login", json={"username": "creator-one", "password": "wrong-password"}
        )
        assert wrong_username.status_code == wrong_password.status_code == 401
        assert wrong_username.json()["detail"] == wrong_password.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_me_returns_creator_for_valid_access_token_and_rejects_missing_or_wrong_type(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})
        login = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        access_token = login.json()["access_token"]
        refresh_token = login.json()["refresh_token"]

        ok = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert ok.status_code == 200
        assert ok.json()["username"] == "creator-one"

        assert (await client.get("/api/v1/auth/me")).status_code == 401

        # A refresh token must not work where an access token is required.
        wrong_type = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
        assert wrong_type.status_code == 401
        assert wrong_type.json()["detail"] == "Invalid token type"


@pytest.mark.asyncio
async def test_refresh_issues_new_tokens_and_rejects_access_token_used_as_refresh(empty_creator_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": "creator-one", "password": "correct-password"})
        login = await client.post("/api/v1/auth/login", json={"username": "creator-one", "password": "correct-password"})
        access_token = login.json()["access_token"]
        refresh_token = login.json()["refresh_token"]

        refreshed = await client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"})
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"] != access_token
        assert refreshed.json()["refresh_token"] != refresh_token

        # An access token must not work where a refresh token is required —
        # the opposite direction of the /me check above.
        wrong_type = await client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {access_token}"})
        assert wrong_type.status_code == 401
        assert wrong_type.json()["detail"] == "Invalid token type"


@pytest.mark.asyncio
async def test_security_headers_present_on_every_response(empty_creator_database):
    """Auditoria: seção 3 (segurança mínima). Nenhum header de segurança
    existia antes desta auditoria — app/main.py's add_security_headers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")  # 401, but headers apply regardless of status
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"


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
