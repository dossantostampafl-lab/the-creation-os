from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.entities import Creator
from app.models.perception import PerceptionSource

pytestmark = pytest.mark.integration


def token(subject: str) -> str:
    return jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )


@pytest.fixture
async def perception_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE creator_notifications, perception_runs, perception_sources, opportunity_evidence, opportunities, "
                "opportunity_observations, automation_executions, registered_capabilities, "
                "chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        session.add(
            PerceptionSource(
                id=source_id,
                name="fixture-perception-source",
                universe="finance",
                provider="fixture_finance",
                capability_name="collect_observations",
                connector_name="opportunity",
                enabled=True,
                schedule_interval_seconds=900,
                minimum_interval_seconds=1,
                max_consecutive_failures=3,
                failure_count=0,
                config_json={},
                next_run_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    yield factory, creator_id, source_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client(perception_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def auth(creator_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(creator_id)}", "X-Correlation-ID": str(uuid.uuid4())}


@pytest.mark.asyncio
async def test_perception_http_collects_discovers_ranks_and_notifies(client, perception_database):
    _, creator_id, source_id = perception_database
    headers = auth(creator_id)

    listed = await client.get("/api/v1/perception/sources", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == source_id for item in listed.json())

    run = await client.post(f"/api/v1/perception/sources/{source_id}/run", headers=headers)
    assert run.status_code == 200
    body = run.json()
    assert body["run"]["status"] == "succeeded"
    assert body["observations_count"] == 2
    assert body["opportunities_count"] >= 1
    assert body["notifications_count"] == 1

    ranking = await client.get("/api/v1/opportunities/ranking", headers=headers)
    assert ranking.status_code == 200
    assert ranking.json()[0]["status"] == "pending_creator_review"

    notifications = await client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    assert notifications.json()[0]["status"] == "unread"

    read = await client.post(f"/api/v1/notifications/{notifications.json()[0]['id']}/read", headers=headers)
    assert read.status_code == 200
    assert read.json()["status"] == "read"

    chronicles = await client.get("/api/v1/chronicles?limit=30", headers=headers)
    event_types = {item["event_type"] for item in chronicles.json()}
    assert {"perception.collection.succeeded", "opportunity.ranking.updated", "creator.notification.created"} <= event_types


@pytest.mark.asyncio
async def test_perception_governance_denial_does_not_collect(client, perception_database):
    _, creator_id, source_id = perception_database
    headers = auth(creator_id)

    disabled = await client.post("/api/v1/automation/capabilities/perception.source.collect/disable", headers=headers)
    assert disabled.status_code == 200

    denied = await client.post(f"/api/v1/perception/sources/{source_id}/run", headers=headers)
    assert denied.status_code == 409
    assert denied.json()["code"] == "CAPABILITY_DISABLED"

    runs = await client.get(f"/api/v1/perception/sources/{source_id}/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json() == []
