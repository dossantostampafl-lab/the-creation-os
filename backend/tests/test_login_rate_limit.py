"""Lote: CORS por ambiente + rate limiting no login (Parte B). Tests the
real fixed-window Redis counter wired into POST /api/v1/auth/login —
against the real Redis instance (settings.redis_url), not mocked.

Uses a small max_attempts/window_seconds via a dependency override
(app.dependency_overrides[get_login_rate_limiter]) rather than the
production default (10/60s) — otherwise the "window resets" test would
need to sleep 60+ real seconds. Documented here as test-only, not a
silently-diverged production value: app/config.py's real defaults are
untouched.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.rate_limit import LoginRateLimiter, get_login_rate_limiter
from app.config import settings
from app.db.session import get_session
from app.main import app

pytestmark = pytest.mark.integration

TEST_MAX_ATTEMPTS = 2
TEST_WINDOW_SECONDS = 2


@pytest.fixture
async def rate_limited_creator_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE creator RESTART IDENTITY CASCADE"))

    async def override_session():
        async with factory() as session:
            yield session

    async def override_rate_limiter():
        redis = Redis.from_url(settings.redis_url)
        try:
            yield LoginRateLimiter(redis, max_attempts=TEST_MAX_ATTEMPTS, window_seconds=TEST_WINDOW_SECONDS)
        finally:
            await redis.aclose()

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_login_rate_limiter] = override_rate_limiter
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_exceeding_the_window_returns_429_with_a_generic_message(rate_limited_creator_database):
    username = f"creator-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": username, "password": "correct-password"})

        # TEST_MAX_ATTEMPTS (2) wrong-password attempts: both 401, neither
        # rate-limited yet.
        for _ in range(TEST_MAX_ATTEMPTS):
            response = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
            assert response.status_code == 401

        # The next (N+1th) attempt is rejected by the limiter itself, before
        # even reaching AuthService.login() — still 401-shaped credentials
        # would also be wrong, but this must be 429, not 401.
        limited = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
        assert limited.status_code == 429
        detail = limited.json()["detail"]
        assert "attempt" in detail.lower()
        # Generic: no attempt count, no remaining-time hint for an attacker
        # to calibrate against.
        assert not any(character.isdigit() for character in detail)


@pytest.mark.asyncio
async def test_window_resets_automatically_after_the_configured_time(rate_limited_creator_database):
    username = f"creator-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": username, "password": "correct-password"})

        for _ in range(TEST_MAX_ATTEMPTS):
            await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
        limited = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
        assert limited.status_code == 429

        await asyncio.sleep(TEST_WINDOW_SECONDS + 1)  # real wait past the real window, not mocked

        recovered = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
        assert recovered.status_code == 401  # rejected for wrong credentials again, not 429 — the limiter reset


@pytest.mark.asyncio
async def test_successful_login_does_not_count_against_the_limit(rate_limited_creator_database):
    username = f"creator-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json={"username": username, "password": "correct-password"})

        # TEST_MAX_ATTEMPTS successful logins in a row must never trip the
        # limiter — only failures count.
        for _ in range(TEST_MAX_ATTEMPTS + 3):
            response = await client.post("/api/v1/auth/login", json={"username": username, "password": "correct-password"})
            assert response.status_code == 200

        # A prior failure followed by a success must also clear that
        # failure — the next wrong-password attempt starts a fresh count,
        # not "one away from the limit".
        wrong = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
        assert wrong.status_code == 401
        success = await client.post("/api/v1/auth/login", json={"username": username, "password": "correct-password"})
        assert success.status_code == 200
        for _ in range(TEST_MAX_ATTEMPTS):
            response = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
            assert response.status_code == 401  # not 429 — the earlier failure was cleared by the success
