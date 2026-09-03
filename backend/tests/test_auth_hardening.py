from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.session import get_session
from app.main import app

pytestmark = pytest.mark.integration

CREDENTIALS = {"username": "sovereign", "password": "sovereign-password"}


@pytest.fixture
async def auth_client():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"))
    redis: Redis = Redis.from_url(settings.redis_url)
    await redis.delete(*[key async for key in redis.scan_iter(match="auth:*")] or ["auth:noop"])

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/bootstrap", json=CREDENTIALS)
        yield client
    app.dependency_overrides.clear()
    await redis.aclose()
    await engine.dispose()


async def login(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json=CREDENTIALS)
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_refresh_token_rotates_and_cannot_be_replayed(auth_client):
    tokens = await login(auth_client)
    headers = {"Authorization": f"Bearer {tokens['refresh_token']}"}

    rotated = await auth_client.post("/api/v1/auth/refresh", headers=headers)
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]

    replayed = await auth_client.post("/api/v1/auth/refresh", headers=headers)
    assert replayed.status_code == 401
    assert replayed.json()["detail"] == "Refresh token is revoked or already used"


@pytest.mark.asyncio
async def test_logout_revokes_outstanding_refresh_tokens(auth_client):
    tokens = await login(auth_client)
    logout = await auth_client.post("/api/v1/auth/logout",
                                    headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert logout.status_code == 204

    refreshed = await auth_client.post("/api/v1/auth/refresh",
                                       headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_login_is_blocked_after_repeated_failures(auth_client):
    previous = settings.login_max_failures
    settings.login_max_failures = 3
    try:
        for _ in range(3):
            failed = await auth_client.post("/api/v1/auth/login",
                                            json={**CREDENTIALS, "password": "wrong-password"})
            assert failed.status_code == 401
        blocked = await auth_client.post("/api/v1/auth/login", json=CREDENTIALS)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "Too many failed login attempts"
    finally:
        settings.login_max_failures = previous


@pytest.mark.asyncio
async def test_successful_login_clears_failure_counter(auth_client):
    previous = settings.login_max_failures
    settings.login_max_failures = 3
    try:
        await auth_client.post("/api/v1/auth/login", json={**CREDENTIALS, "password": "wrong-password"})
        await login(auth_client)
        for _ in range(2):
            await auth_client.post("/api/v1/auth/login", json={**CREDENTIALS, "password": "wrong-password"})
        assert (await auth_client.post("/api/v1/auth/login", json=CREDENTIALS)).status_code == 200
    finally:
        settings.login_max_failures = previous


@pytest.mark.asyncio
async def test_correlation_id_is_generated_when_absent(auth_client):
    response = await auth_client.post("/api/v1/auth/login", json=CREDENTIALS)
    assert len(response.headers["X-Correlation-ID"]) == 36
    echoed = await auth_client.post("/api/v1/auth/login", json=CREDENTIALS,
                                    headers={"X-Correlation-ID": "provided-id"})
    assert echoed.headers["X-Correlation-ID"] == "provided-id"
