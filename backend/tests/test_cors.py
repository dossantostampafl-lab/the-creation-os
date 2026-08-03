"""Lote: CORS por ambiente + rate limiting no login (Parte A). Confirms
CORSMiddleware's real, wired-up behavior over the ASGI app (not just the
config values in isolation) — an unlisted origin gets no CORS allow
headers, a listed one does — plus the two config-level guarantees:
CORS_ALLOWED_ORIGINS is mandatory in production, and allow_credentials
never coexists with a literal wildcard origin.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic.v1 import ValidationError

from app.config import Settings, resolve_cors_middleware_kwargs
from app.main import app

pytestmark = pytest.mark.integration

_REQUIRED_SETTINGS_KWARGS = dict(
    app_env="production",
    secret_key="test-secret-key-at-least-32-characters",
    creator_bootstrap_username="creator",
    creator_bootstrap_password="test-password",
    database_url="postgresql+asyncpg://user:pass@localhost/db",
    redis_url="redis://localhost:6379/0",
)


@pytest.mark.asyncio
async def test_allowed_origin_receives_cors_allow_header():
    # Matches the dev/test default in Settings.cors_allowed_origins_list
    # (no CORS_ALLOWED_ORIGINS set in this test environment).
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_disallowed_origin_receives_no_cors_allow_header():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live", headers={"Origin": "http://evil.example"})
    # The request itself isn't blocked server-side (CORS is a browser-enforced
    # policy, not a server firewall) — but the response must not carry an
    # Access-Control-Allow-Origin naming (or matching) the disallowed origin,
    # which is what makes a real browser refuse to expose it to page JS.
    assert response.headers.get("access-control-allow-origin") != "http://evil.example"


def test_production_requires_cors_allowed_origins():
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(cors_allowed_origins=None, **_REQUIRED_SETTINGS_KWARGS)  # type: ignore[call-arg]


def test_production_accepts_explicit_cors_allowed_origins():
    settings = Settings(cors_allowed_origins="https://real-frontend.example", **_REQUIRED_SETTINGS_KWARGS)  # type: ignore[call-arg]
    assert settings.cors_allowed_origins_list == ["https://real-frontend.example"]


def test_wildcard_origin_never_coexists_with_allow_credentials():
    wildcard_kwargs = resolve_cors_middleware_kwargs(["*"])
    assert wildcard_kwargs["allow_credentials"] is False

    explicit_kwargs = resolve_cors_middleware_kwargs(["http://localhost:5173"])
    assert explicit_kwargs["allow_credentials"] is True

    mixed_kwargs = resolve_cors_middleware_kwargs(["http://localhost:5173", "*"])
    assert mixed_kwargs["allow_credentials"] is False
