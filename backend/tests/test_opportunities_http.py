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
from app.models.entities import Creator

pytestmark = pytest.mark.integration


def token(subject: str) -> str:
    return jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )


@pytest.fixture
async def opportunity_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE opportunity_evidence, opportunities, opportunity_observations, registered_capabilities, "
                "chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
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
async def client(opportunity_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def auth(creator_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(creator_id)}", "X-Correlation-ID": str(uuid.uuid4())}


def observation(event_type: str = "volume_anomaly") -> dict:
    return {
        "universe": "finance",
        "source": "fixture.market",
        "subject": "ACME",
        "event_type": event_type,
        "title": f"ACME {event_type}",
        "summary": "Controlled fixture signal for investigation.",
        "source_reliability": 0.82,
        "correlation_key": "acme:opportunity",
        "normalized_data": {"volume_ratio": 2.7},
        "evidence": {"fixture": True, "financial_execution": False},
    }


@pytest.mark.asyncio
async def test_opportunity_http_flow_creates_inception_and_audits(client, opportunity_database):
    _, creator_id = opportunity_database
    headers = auth(creator_id)

    discovery = await client.post(
        "/api/v1/opportunities/discovery/run",
        headers=headers,
        json={"observations": [observation(), observation("volatility_increase")]},
    )
    assert discovery.status_code == 200
    opportunity = discovery.json()["opportunities"][0]
    assert opportunity["status"] == "pending_creator_review"
    assert opportunity["priority_score"] > 0
    assert len(opportunity["evidence"]["observations"]) == 2

    ranking = await client.get("/api/v1/opportunities/ranking", headers=headers)
    assert ranking.status_code == 200
    assert ranking.json()[0]["id"] == opportunity["id"]

    approved = await client.post(f"/api/v1/opportunities/{opportunity['id']}/approve", headers=headers, json={"reason": "investigate"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    converted = await client.post(f"/api/v1/opportunities/{opportunity['id']}/convert-to-inception", headers=headers)
    assert converted.status_code == 200
    assert converted.json()["status"] == "converted_to_inception"
    assert converted.json()["inception_id"]

    duplicate = await client.post(f"/api/v1/opportunities/{opportunity['id']}/convert-to-inception", headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "OPPORTUNITY_INCEPTION_ALREADY_CREATED"

    chronicles = await client.get("/api/v1/chronicles?limit=20", headers=headers)
    event_types = {item["event_type"] for item in chronicles.json()}
    assert {"opportunity.detected", "opportunity.approved", "opportunity.converted_to_inception"} <= event_types


@pytest.mark.asyncio
async def test_disabled_discovery_capability_denies_without_persistence(client, opportunity_database):
    _, creator_id = opportunity_database
    headers = auth(creator_id)

    disabled = await client.post("/api/v1/automation/capabilities/opportunity.discovery.run/disable", headers=headers)
    assert disabled.status_code == 200

    denied = await client.post("/api/v1/opportunities/discovery/run", headers=headers, json={"observations": [observation()]})
    assert denied.status_code == 409
    assert denied.json()["code"] == "CAPABILITY_DISABLED"

    assert (await client.get("/api/v1/observations", headers=headers)).json() == []
    assert (await client.get("/api/v1/opportunities", headers=headers)).json() == []
    chronicles = await client.get("/api/v1/chronicles?limit=20", headers=headers)
    event_types = {item["event_type"] for item in chronicles.json()}
    assert "capability.execution.denied" in event_types
