"""A conversation with DEUS end to end: HTTP route, service, database and a FreeLLMAPI-shaped upstream.

The only fake is the upstream gateway (an httpx mock transport speaking the OpenAI chat format, with no key).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text

from app.api import deus as deus_api
from app.config import settings
from app.db.session import get_session
from app.inference.contracts import ProviderModelProfile
from app.inference.freellmapi_provider import FreeLLMAPIProvider
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter
from app.main import app
from app.models.entities import Conversation, Creator


def _router(handler):
    registry = ProviderRegistry()
    registry.register(FreeLLMAPIProvider(default_model="auto", base_url="http://gateway/v1",
                                         transport=httpx.MockTransport(handler)))
    registry.register_model_profile(ProviderModelProfile(provider="freellmapi", model="auto",
                                                         capabilities=frozenset({"text"}), is_default=True))
    return ModelRouter(registry)


async def _talk(stf_db, monkeypatch, handler, content="Deus, você está me ouvindo?"):
    _, factory = stf_db
    creator_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="x", is_active=True))
        await session.flush()
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="t", status="active"))
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "")
    monkeypatch.setattr(settings, "sovereign_creator_id", creator_id)
    monkeypatch.setattr(deus_api, "build_model_router", lambda: _router(handler))
    app.dependency_overrides[get_session] = override_session
    token = jwt.encode({"sub": creator_id, "type": "access", "jti": str(uuid.uuid4()),
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       settings.secret_key.get_secret_value(), algorithm="HS256")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            url = f"/api/v1/conversations/{conversation_id}"
            response = await client.post(f"{url}/deus", json={"content": content},
                                         headers={"Authorization": f"Bearer {token}"})
            messages = await client.get(f"{url}/messages", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()
    return response, messages, factory


async def test_the_creator_talks_to_deus_through_a_keyless_gateway(stf_db, monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": "auto", "choices": [
            {"message": {"role": "assistant", "content": "Estou ouvindo você."}, "finish_reason": "stop"}],
            "usage": {"total_tokens": len(body["messages"])}})

    response, messages, factory = await _talk(stf_db, monkeypatch, handler)
    assert response.status_code == 201, response.text
    assert response.json()["response"] == "Estou ouvindo você."
    assert all("authorization" not in request.headers for request in seen)  # no key, no Authorization header
    assert [m["role"] for m in messages.json()] == ["creator", "deus"]
    async with factory() as session:
        events = (await session.execute(text("SELECT event_type FROM chronicles"))).scalars().all()
    assert "deus_response_generated" in events


async def test_when_the_gateway_is_down_deus_says_so_with_503(stf_db, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    response, messages, _ = await _talk(stf_db, monkeypatch, handler)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["provider"] == "freellmapi"
    assert detail["code"] == "INFERENCE_UPSTREAM_RESPONSE_ERROR"
    assert "provedor de inferência" in detail["message"]
    assert detail["retryable"] is False
