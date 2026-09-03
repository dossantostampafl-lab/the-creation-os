from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.entities import Conversation, Creator

pytestmark = pytest.mark.integration


def token(subject: str, kind: str = "access") -> str:
    return jwt.encode({"sub": subject, "type": kind, "jti": str(uuid.uuid4()),
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                      settings.secret_key.get_secret_value(), algorithm="HS256")


@pytest.fixture
async def http_database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"))
    creator_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        session.add_all([Creator(id=creator_id, username="creator", password_hash="unused", is_active=True),
                         Creator(id=other_id, username="other", password_hash="unused", is_active=True)])
        await session.commit()

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    previous_sovereign = settings.sovereign_creator_id
    settings.sovereign_creator_id = creator_id
    yield factory, creator_id, other_id
    settings.sovereign_creator_id = previous_sovereign
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client(http_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def auth(creator_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(creator_id)}", "X-Correlation-ID": str(uuid.uuid4())}


@pytest.mark.asyncio
async def test_authentication_validation_and_health(client, http_database):
    _, creator_id, _ = http_database
    assert (await client.get("/api/v1/health/live")).status_code == 200
    assert (await client.get("/api/v1/conversations")).status_code == 401
    assert (await client.get("/api/v1/conversations", headers={"Authorization": "Bearer invalid"})).status_code == 401
    assert (await client.get("/api/v1/conversations/not-a-uuid", headers=auth(creator_id))).status_code == 422
    assert (await client.post("/api/v1/conversations", headers=auth(creator_id), json={"title": "x"})).status_code == 422


@pytest.mark.asyncio
async def test_all_living_core_http_actions(client, http_database):
    _, creator_id, _ = http_database
    headers = auth(creator_id)
    created = await client.post("/api/v1/conversations", headers=headers, json={"title": "HTTP conversation"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert (await client.get("/api/v1/conversations", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)).status_code == 200
    message = await client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers,
                                json={"content": "Explicit intent", "metadata": {"safe": True}})
    assert message.status_code == 201
    assert message.json()["correlation_id"] == headers["X-Correlation-ID"]
    inception = await client.post("/api/v1/inceptions", headers=headers, json={
        "conversation_id": conversation_id, "source_message_id": message.json()["id"],
        "title": "HTTP intent", "description": "Explicit inception"})
    assert inception.status_code == 201
    inception_id = inception.json()["id"]
    assert (await client.get("/api/v1/inceptions", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/inceptions/{inception_id}", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/inceptions/{inception_id}/submit", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/inceptions/{inception_id}/approve", headers=headers, json={"reason": "yes"})).status_code == 200
    invalid = await client.post(f"/api/v1/inceptions/{inception_id}/reject", headers=headers, json={"reason": "late"})
    assert invalid.status_code == 409
    mission = await client.post("/api/v1/missions", headers=headers, json={
        "inception_id": inception_id, "title": "HTTP mission", "objective": "Prove HTTP"})
    assert mission.status_code == 201
    mission_id = mission.json()["id"]
    assert (await client.get("/api/v1/missions", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/missions/{mission_id}", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/missions/{mission_id}/plan", headers=headers,
                              json={"strategy": "Central Core plan", "completion_criteria": {"done": True}})).status_code == 200
    assert (await client.post(f"/api/v1/missions/{mission_id}/validate", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/missions/{mission_id}/authorize", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/missions/{mission_id}/cancel", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/conversations/{conversation_id}/close", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/conversations/{conversation_id}/archive", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_rejection_path_and_unapproved_mission_block(client, http_database):
    _, creator_id, _ = http_database
    headers = auth(creator_id)
    conversation = (await client.post("/api/v1/conversations", headers=headers, json={"title": "Rejected path"})).json()
    message = (await client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers,
                                 json={"content": "Intent"})).json()
    inception = (await client.post("/api/v1/inceptions", headers=headers, json={
        "conversation_id": conversation["id"], "source_message_id": message["id"],
        "title": "Rejected", "description": "No"})).json()
    await client.post(f"/api/v1/inceptions/{inception['id']}/submit", headers=headers)
    assert (await client.post(f"/api/v1/inceptions/{inception['id']}/reject", headers=headers, json={})).status_code == 200
    blocked = await client.post("/api/v1/missions", headers=headers, json={
        "inception_id": inception["id"], "title": "Blocked mission", "objective": "must fail"})
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_sovereign_creator_and_idor(client, http_database):
    factory, creator_id, other_id = http_database
    foreign_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Conversation(id=foreign_id, creator_id=other_id, title="Foreign", status="active"))
        await session.commit()
    assert (await client.get(f"/api/v1/conversations/{foreign_id}", headers=auth(creator_id))).status_code == 404
    assert (await client.post(f"/api/v1/conversations/{foreign_id}/messages", headers=auth(creator_id),
                              json={"content": "IDOR"})).status_code == 404
    assert (await client.get("/api/v1/conversations", headers=auth(other_id))).status_code == 403


@pytest.mark.asyncio
async def test_me_returns_the_authenticated_creator(client, http_database):
    _, creator_id, _ = http_database
    response = await client.get("/api/v1/auth/me", headers=auth(creator_id))
    assert response.status_code == 200
    assert response.json()["id"] == creator_id
    assert response.json()["username"] == "creator"


@pytest.mark.asyncio
async def test_configured_sovereign_creator_id_is_enforced(client, http_database):
    _, creator_id, other_id = http_database
    settings.sovereign_creator_id = other_id
    assert (await client.get("/api/v1/conversations", headers=auth(creator_id))).status_code == 403
    assert (await client.get("/api/v1/conversations", headers=auth(other_id))).status_code == 200
    settings.sovereign_creator_id = creator_id


@pytest.mark.asyncio
async def test_chronicles_and_pulse(client, http_database):
    _, creator_id, other_id = http_database
    headers = auth(creator_id)
    conversation = (await client.post("/api/v1/conversations", headers=headers, json={"title": "Observability"})).json()
    await client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers, json={"content": "Intent"})

    chronicles = await client.get("/api/v1/chronicles", headers=headers)
    assert chronicles.status_code == 200
    assert [event["event_type"] for event in chronicles.json()] == ["conversation_created", "conversation_message_added"]
    assert chronicles.json()[0]["previous_hash"] is None
    assert (await client.get("/api/v1/chronicles?limit=1&offset=1", headers=headers)).json()[0]["event_type"] == "conversation_message_added"

    verified = await client.get("/api/v1/chronicles/verify", headers=headers)
    assert verified.status_code == 200
    assert verified.json()["valid"] is True

    pulse = await client.get("/api/v1/pulse", headers=headers)
    assert pulse.status_code == 200
    body = pulse.json()
    assert body["status"] == "healthy"
    assert body["database"]["available"] is True
    assert body["chronicles_chain"]["valid"] is True
    assert body["pending_inceptions"] == 0

    for path in ("/api/v1/chronicles", "/api/v1/chronicles/verify", "/api/v1/pulse"):
        assert (await client.get(path, headers=auth(other_id))).status_code == 403


@pytest.mark.asyncio
async def test_chronicles_verify_detects_tampering(client, http_database):
    factory, creator_id, _ = http_database
    headers = auth(creator_id)
    await client.post("/api/v1/conversations", headers=headers, json={"title": "Tampered"})
    async with factory() as session:
        await session.execute(text("UPDATE chronicles SET payload_json = '{\"injected\": true}'"))
        await session.commit()
    verified = await client.get("/api/v1/chronicles/verify", headers=headers)
    assert verified.json()["valid"] is False
    assert "invalid event hash" in verified.json()["message"]


@pytest.mark.asyncio
async def test_future_states_have_no_public_routes(client, http_database):
    _, creator_id, _ = http_database
    headers = auth(creator_id)
    for action in ("distribute", "execute", "manifest"):
        assert (await client.post(f"/api/v1/missions/{uuid.uuid4()}/{action}", headers=headers)).status_code == 404
