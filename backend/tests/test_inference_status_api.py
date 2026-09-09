from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.living_core import actor
from app.core.domain import Actor
from app.main import app


@pytest.mark.asyncio
async def test_inference_status_route_is_protected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/system/inference")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inference_status_route_returns_safe_unconfigured_snapshot_for_fake_provider() -> None:
    app.dependency_overrides[actor] = lambda: Actor(id="creator", role="creator")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/system/inference")
    finally:
        app.dependency_overrides.pop(actor, None)

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "configured_provider": "fake",
        "providers": [],
    }
