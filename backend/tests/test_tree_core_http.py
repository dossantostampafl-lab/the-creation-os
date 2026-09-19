from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.entities import Conversation, Creator, Inception, Message, Mission

pytestmark = pytest.mark.integration


def token(subject: str) -> str:
    return jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )


def auth(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(subject)}"}


@pytest.fixture
async def tree_http_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE agent_capabilities, capabilities, tasks, agents, universes, chronicles, "
            "mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
        ))
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    yield factory, creator_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def tree_client(tree_http_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def mission(factory, creator_id: str, status: str) -> str:
    conversation_id, message_id, inception_id, mission_id = (str(uuid.uuid4()) for _ in range(4))
    async with factory() as session:
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="Tree Core", status="active"))
        session.add(Message(id=message_id, conversation_id=conversation_id, role="creator", actor_id=creator_id,
                            correlation_id=str(uuid.uuid4()), content="intent", route="central", metadata_json={}))
        session.add(Inception(id=inception_id, conversation_id=conversation_id, source_message_id=message_id,
                              title="Tree Core", description="selection", status="approved",
                              trinity_assessment_json={}))
        session.add(Mission(id=mission_id, inception_id=inception_id, creator_id=creator_id, title="Select",
                            objective="Select only", status=status, authorization_json={}))
        await session.commit()
    return mission_id


@pytest.mark.asyncio
async def test_all_twelve_tree_core_endpoints_and_deterministic_match(tree_client, tree_http_database):
    factory, creator_id = tree_http_database
    headers = auth(creator_id)

    capability = await tree_client.post("/api/v1/capabilities", headers=headers,
                                        json={"name": "Analysis", "description": "Analyze"})
    assert capability.status_code == 201
    capability_id = capability.json()["id"]
    assert (await tree_client.get("/api/v1/capabilities", headers=headers)).status_code == 200

    first = await tree_client.post("/api/v1/agents", headers=headers,
                                   json={"name": "Alpha", "description": "A", "universe": "central", "priority": 5})
    second = await tree_client.post("/api/v1/agents", headers=headers,
                                    json={"name": "Beta", "description": "B", "universe": "central", "priority": 5})
    assert first.status_code == second.status_code == 201
    first_id, second_id = first.json()["id"], second.json()["id"]

    listed = await tree_client.get("/api/v1/agents", headers=headers)
    assert listed.status_code == 200 and len(listed.json()) == 2
    assert (await tree_client.get(f"/api/v1/agents/{first_id}", headers=headers)).status_code == 200
    patched = await tree_client.patch(f"/api/v1/agents/{second_id}", headers=headers, json={"priority": 10})
    assert patched.status_code == 200 and patched.json()["priority"] == 10

    for agent_id in (first_id, second_id):
        linked = await tree_client.post(f"/api/v1/agents/{agent_id}/capabilities", headers=headers,
                                        json={"capability_id": capability_id})
        assert linked.status_code == 200
        assert (await tree_client.post(f"/api/v1/agents/{agent_id}/heartbeat", headers=headers)).status_code == 200

    assert (await tree_client.post(f"/api/v1/agents/{first_id}/disable", headers=headers)).status_code == 200
    assert (await tree_client.post(f"/api/v1/agents/{first_id}/enable", headers=headers)).status_code == 200
    assert (await tree_client.post(f"/api/v1/agents/{first_id}/heartbeat", headers=headers)).status_code == 200

    removed = await tree_client.delete(f"/api/v1/agents/{first_id}/capabilities/{capability_id}", headers=headers)
    assert removed.status_code == 200
    assert (await tree_client.post(f"/api/v1/agents/{first_id}/capabilities", headers=headers,
                                   json={"capability_id": capability_id})).status_code == 200

    mission_id = await mission(factory, creator_id, "authorized")
    matched = await tree_client.post("/api/v1/tree-core/match", headers=headers,
                                     json={"mission_id": mission_id, "required_capabilities": ["ANALYSIS"]})
    assert matched.status_code == 200
    assert [item["id"] for item in matched.json()["agents"]] == [second_id, first_id]


@pytest.mark.asyncio
async def test_tree_core_http_security_validation_and_errors(tree_client, tree_http_database):
    factory, creator_id = tree_http_database
    headers = auth(creator_id)
    other_headers = auth(str(uuid.uuid4()))

    assert (await tree_client.get("/api/v1/agents")).status_code == 401
    assert (await tree_client.get("/api/v1/agents", headers=other_headers)).status_code == 403
    assert (await tree_client.get("/api/v1/agents/not-a-uuid", headers=headers)).status_code == 422
    assert (await tree_client.get(f"/api/v1/agents/{uuid.uuid4()}", headers=headers)).status_code == 404
    assert (await tree_client.post("/api/v1/agents", headers=headers, json={
        "name": "unsafe", "universe": "central", "role": "creator", "status": "idle",
        "enabled": False, "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    })).status_code == 422
    assert (await tree_client.post(f"/api/v1/agents/{uuid.uuid4()}/capabilities", headers=headers,
                                   json={"capability_id": "not-a-uuid"})).status_code == 422

    created = await tree_client.post("/api/v1/capabilities", headers=headers, json={"name": "Analysis"})
    assert created.status_code == 201
    assert (await tree_client.post("/api/v1/capabilities", headers=headers,
                                   json={"name": "  ANALYSIS  "})).status_code == 409

    agent = await tree_client.post("/api/v1/agents", headers=headers,
                                   json={"name": "Agent", "universe": "central"})
    agent_id = agent.json()["id"]
    body = {"capability_id": created.json()["id"]}
    assert (await tree_client.post(f"/api/v1/agents/{agent_id}/capabilities", headers=headers,
                                   json=body)).status_code == 200
    assert (await tree_client.post(f"/api/v1/agents/{agent_id}/capabilities", headers=headers,
                                   json=body)).status_code == 409

    unauthorized_mission = await mission(factory, creator_id, "planned")
    rejected = await tree_client.post("/api/v1/tree-core/match", headers=headers,
                                      json={"mission_id": unauthorized_mission, "required_capabilities": ["analysis"]})
    assert rejected.status_code == 409
