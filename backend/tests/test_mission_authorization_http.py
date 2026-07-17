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
from app.models.entities import Conversation, Creator, Inception, Message, Mission

pytestmark = pytest.mark.integration


def token(subject: str) -> str:
    return jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )


@pytest.fixture
async def mission_authorization_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE mission_authorizations, automation_executions, registered_capabilities, chronicles, "
                "mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    mission_id = str(uuid.uuid4())
    async with factory() as session:
        creator = Creator(id=creator_id, username="creator", password_hash="unused", is_active=True)
        conversation = Conversation(id=str(uuid.uuid4()), creator_id=creator_id, title="Mission Authorization", status="active")
        message = Message(id=str(uuid.uuid4()), conversation_id=conversation.id, role="god", actor_id=creator_id, correlation_id=str(uuid.uuid4()), content="Mission", route="mission")
        inception = Inception(id=str(uuid.uuid4()), conversation_id=conversation.id, source_message_id=message.id, title="Finalizar projeto de demonstracao", description="Demo", status="approved")
        mission = Mission(id=mission_id, inception_id=inception.id, creator_id=creator_id, title="Finalizar projeto de demonstracao", objective="Finalizar projeto de demonstracao", status="drafted")
        session.add(creator)
        await session.flush()
        session.add(conversation)
        await session.flush()
        session.add(message)
        await session.flush()
        session.add(inception)
        await session.flush()
        session.add(mission)
        await session.commit()

    async def override_session():
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    yield creator_id, mission_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client(mission_authorization_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def auth(creator_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(creator_id)}", "X-Correlation-ID": str(uuid.uuid4())}


def authorization_payload() -> dict:
    return {
        "project_id": "local",
        "scope": {"actions": ["read_project_files", "modify_project_files", "run_tests", "update_documentation", "create_local_commit"]},
        "allowed_capabilities": ["opportunity.observation.collect"],
        "allowed_resources": ["project/*"],
        "restrictions": {"denied_actions": ["git_push", "deploy"]},
    }


def automation_payload(mission_id: str, action: str) -> dict:
    return {
        "connector_id": "opportunity",
        "capability": "collect_observations",
        "payload": {},
        "timeout_seconds": 5,
        "idempotency_key": str(uuid.uuid4()),
        "mission_id": mission_id,
        "project_id": "local",
        "action": action,
        "resource": "project/file.txt",
        "reason": "Smoke test",
    }


@pytest.mark.asyncio
async def test_mission_authorization_http_flow_and_scope_violation(client, mission_authorization_database):
    creator_id, mission_id = mission_authorization_database
    headers = auth(creator_id)

    denied_before = await client.post("/api/v1/automation/execute", headers=headers, json=automation_payload(mission_id, "read_project_files"))
    assert denied_before.status_code == 409
    assert denied_before.json()["code"] == "MISSION_AUTHORIZATION_REQUIRED"

    requested = await client.post(f"/api/v1/missions/{mission_id}/authorization/request", headers=headers, json=authorization_payload())
    assert requested.status_code == 201
    assert requested.json()["status"] == "pending"

    pending_denied = await client.post("/api/v1/automation/execute", headers=headers, json=automation_payload(mission_id, "read_project_files"))
    assert pending_denied.status_code == 409
    assert pending_denied.json()["code"] == "MISSION_NOT_AUTHORIZED"

    approved = await client.post(f"/api/v1/missions/{mission_id}/authorization/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "authorized"

    allowed = await client.post("/api/v1/automation/execute", headers=headers, json=automation_payload(mission_id, "read_project_files"))
    assert allowed.status_code == 201
    assert allowed.json()["status"] == "SUCCEEDED"

    blocked = await client.post("/api/v1/automation/execute", headers=headers, json=automation_payload(mission_id, "git_push"))
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MISSION_SCOPE_VIOLATION"

    chronicles = await client.get("/api/v1/chronicles?limit=40", headers=headers)
    event_types = {item["event_type"] for item in chronicles.json()}
    assert {"mission.authorization.requested", "mission.authorization.approved", "mission.action.authorized", "mission.action.denied", "mission.scope.exceeded"} <= event_types


@pytest.mark.asyncio
async def test_mission_authorization_revoke_preserves_history(client, mission_authorization_database):
    creator_id, mission_id = mission_authorization_database
    headers = auth(creator_id)

    await client.post(f"/api/v1/missions/{mission_id}/authorization/request", headers=headers, json=authorization_payload())
    await client.post(f"/api/v1/missions/{mission_id}/authorization/approve", headers=headers)
    revoked = await client.post(f"/api/v1/missions/{mission_id}/authorization/revoke", headers=headers)

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    latest = await client.get(f"/api/v1/missions/{mission_id}/authorization", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["status"] == "revoked"
