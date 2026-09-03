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
from app.models.entities import Creator

pytestmark = pytest.mark.integration

TRUNCATE = ("TRUNCATE chronicles, conscious_memory, universe_memory, mission_memory, conversation_memory, tasks, "
            "mission_steps, mission_plans, missions, inceptions, messages, conversations, agents, universes, creator "
            "RESTART IDENTITY CASCADE")


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode({"sub": subject, "type": "access", "jti": str(uuid.uuid4()),
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                       settings.secret_key.get_secret_value(), algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def world():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(TRUNCATE))
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, creator_id, other_id
    settings.sovereign_creator_id = previous_sovereign
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_universe_lifecycle_and_duplicate_code(world):
    client, creator_id, _ = world
    headers = auth(creator_id)
    created = await client.post("/api/v1/universes", headers=headers, json={"code": "malkuth", "name": "Malkuth"})
    assert created.status_code == 201
    assert created.json()["active"] is False

    universe_id = created.json()["id"]
    assert (await client.post(f"/api/v1/universes/{universe_id}/activate", headers=headers)).json()["active"] is True
    assert (await client.post(f"/api/v1/universes/{universe_id}/deactivate", headers=headers)).json()["active"] is False

    duplicated = await client.post("/api/v1/universes", headers=headers, json={"code": "malkuth", "name": "Outro"})
    assert duplicated.status_code == 409
    assert [x["code"] for x in (await client.get("/api/v1/universes", headers=headers)).json()] == ["malkuth"]


@pytest.mark.asyncio
async def test_agents_are_scoped_to_a_universe(world):
    client, creator_id, _ = world
    headers = auth(creator_id)
    universe_id = (await client.post("/api/v1/universes", headers=headers,
                                     json={"code": "yesod", "name": "Yesod"})).json()["id"]
    other_universe = (await client.post("/api/v1/universes", headers=headers,
                                        json={"code": "hod", "name": "Hod"})).json()["id"]

    agent = await client.post("/api/v1/agents", headers=headers, json={
        "code": "sophia", "name": "SOPHIA", "universe_id": universe_id, "capabilities": {"plan": True}})
    assert agent.status_code == 201
    assert agent.json()["capabilities_json"] == {"plan": True}

    assert len((await client.get(f"/api/v1/agents?universe_id={universe_id}", headers=headers)).json()) == 1
    assert (await client.get(f"/api/v1/agents?universe_id={other_universe}", headers=headers)).json() == []

    unknown = await client.post("/api/v1/agents", headers=headers, json={
        "code": "ghost", "name": "Ghost", "universe_id": str(uuid.uuid4())})
    assert unknown.status_code == 404
    assert (await client.post(f"/api/v1/agents/{agent.json()['id']}/deactivate", headers=headers)).json()["active"] is False


@pytest.mark.asyncio
async def test_memory_layers_upsert_by_key(world):
    client, creator_id, _ = world
    headers = auth(creator_id)
    conversation_id = (await client.post("/api/v1/conversations", headers=headers,
                                         json={"title": "Memória"})).json()["id"]

    first = await client.put(f"/api/v1/memory/conversation/{conversation_id}", headers=headers,
                             json={"key": "tone", "value": {"style": "direct"}})
    assert first.status_code == 200
    updated = await client.put(f"/api/v1/memory/conversation/{conversation_id}", headers=headers,
                               json={"key": "tone", "value": {"style": "formal"}})
    assert updated.json()["id"] == first.json()["id"]

    entries = (await client.get(f"/api/v1/memory/conversation/{conversation_id}", headers=headers)).json()
    assert entries == [{**entries[0], "key": "tone", "value": {"style": "formal"}}]
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_memory_is_isolated_per_owner_and_layer(world):
    client, creator_id, other_id = world
    headers = auth(creator_id)
    conversation_id = (await client.post("/api/v1/conversations", headers=headers,
                                         json={"title": "Privada"})).json()["id"]
    settings.sovereign_creator_id = other_id
    assert (await client.get(f"/api/v1/memory/conversation/{conversation_id}", headers=auth(other_id))).status_code == 404
    settings.sovereign_creator_id = creator_id

    assert (await client.get(f"/api/v1/memory/mission/{conversation_id}", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/memory/soul/{conversation_id}", headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_conscious_memory_is_embedded_and_listed(world):
    client, creator_id, _ = world
    headers = auth(creator_id)
    recorded = await client.post("/api/v1/memory/conscious", headers=headers, json={
        "source_type": "conversation", "source_id": str(uuid.uuid4()), "content": "O Criador decidiu avançar."})
    assert recorded.status_code == 201
    assert len(recorded.json()["embedding"]) == 8

    assert len((await client.get("/api/v1/memory/conscious?source_type=conversation", headers=headers)).json()) == 1
    assert (await client.get("/api/v1/memory/conscious?source_type=mission", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_domain_changes_are_chronicled(world):
    client, creator_id, _ = world
    headers = auth(creator_id)
    universe_id = (await client.post("/api/v1/universes", headers=headers,
                                     json={"code": "tiferet", "name": "Tiferet"})).json()["id"]
    await client.post(f"/api/v1/universes/{universe_id}/activate", headers=headers)
    await client.post("/api/v1/agents", headers=headers,
                      json={"code": "rockmam", "name": "ROCKMAM", "universe_id": universe_id})
    await client.put(f"/api/v1/memory/universe/{universe_id}", headers=headers,
                     json={"key": "purpose", "value": {"role": "execution"}})

    events = [x["event_type"] for x in (await client.get("/api/v1/chronicles", headers=headers)).json()]
    assert events == ["universe_created", "universe_activated", "agent_created", "universe_memory_written"]
    assert (await client.get("/api/v1/chronicles/verify", headers=headers)).json()["valid"] is True


@pytest.mark.asyncio
async def test_non_sovereign_creator_cannot_reach_the_new_routes(world):
    client, _, other_id = world
    headers = auth(other_id)
    assert (await client.get("/api/v1/universes", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/agents", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/memory/conscious", headers=headers)).status_code == 403
