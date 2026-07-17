from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.decision import MissionDecision
from app.models.entities import Chronicle, Conversation, Creator, Inception, Message, Mission
from app.models.execution import AgentExecution
from app.models.god import GodConversationInteraction
from app.models.manifestation import MissionManifestation
from app.models.rockmam import RockmamPossibilityAssessment
from app.models.sophia import SophiaUnderstanding

pytestmark = pytest.mark.integration


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}", "X-Correlation-ID": str(uuid.uuid4())}


@pytest.fixture
async def trinity_database():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE chronicles, rockmam_possibility_assessments, sophia_understandings, "
                "god_conversation_interactions, mission_manifestations, mission_decision_reasoning, "
                "mission_decisions, mission_consolidations, agent_executions, mission_plans, missions, "
                "inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    potential_id = str(uuid.uuid4())
    direct_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Creator(id=creator_id, username="creator", password_hash="unused", is_active=True))
        await session.commit()
    async with factory() as session:
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title="Trinity", status="active"))
        await session.commit()
    async with factory() as session:
        for interaction_id, interaction_type, message in (
            (potential_id, "POTENTIAL", "Criar sistema"),
            (direct_id, "DIRECT_RESPONSE", "Ola"),
        ):
            creator_message = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                actor_id=creator_id,
                role="creator",
                correlation_id=str(uuid.uuid4()),
                content=message,
                route="god",
                metadata_json={"idempotency_key": interaction_id},
            )
            god_message = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                actor_id="god",
                role="god",
                correlation_id=str(uuid.uuid4()),
                content="GOD response",
                route="god",
                metadata_json={"interaction_type": interaction_type},
            )
            session.add_all([creator_message, god_message])
            await session.flush()
            session.add(
                GodConversationInteraction(
                    id=interaction_id,
                    conversation_id=conversation_id,
                    creator_message_id=creator_message.id,
                    god_message_id=god_message.id,
                    idempotency_key=interaction_id,
                    interaction_type=interaction_type,
                    request_payload={
                        "message": message,
                        "idempotency_key": interaction_id,
                        "policy_version": "v0.7.0",
                        "request_fingerprint": "a" * 64,
                    },
                    response_payload={
                        "conversation_id": conversation_id,
                        "message_id": creator_message.id,
                        "god_message_id": god_message.id,
                        "interaction_type": interaction_type,
                        "reply": {"message": "GOD response", "policy_version": "v0.7.0"},
                        "potential_detected": interaction_type == "POTENTIAL",
                        "next_action": "creator_may_request_trinity_analysis",
                        "fingerprint": "b" * 64,
                    },
                    potential_detected=interaction_type == "POTENTIAL",
                    fingerprint="b" * 64,
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

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    yield factory, {"creator": creator_id, "conversation": conversation_id, "potential": potential_id, "direct": direct_id}
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_trinity_orchestrates_potential_without_creating_domain_objects(trinity_database):
    factory, ids = trinity_database
    path = f"/api/v1/trinity/god-interactions/{ids['potential']}/orchestrate"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(path)).status_code == 401
        created = await client.post(path, headers=auth(ids["creator"]))
        assert created.status_code == 201
        payload = created.json()
        assert payload["god_interaction_id"] == ids["potential"]
        assert payload["interaction_type"] == "POTENTIAL"
        assert payload["assessment_result"] == "REQUIRES_CREATOR"
        assert payload["god_consolidated_result"]["received_by"] == "GOD"
        assert payload["god_consolidated_result"]["creates_inception"] is False
        assert payload["god_consolidated_result"]["creates_mission"] is False

        replay = await client.post(path, headers=auth(ids["creator"]))
        assert replay.status_code == 200
        assert replay.json()["sophia_understanding_id"] == payload["sophia_understanding_id"]
        assert replay.json()["rockmam_assessment_id"] == payload["rockmam_assessment_id"]
        assert replay.json()["understanding_created"] is False
        assert replay.json()["assessment_created"] is False

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(SophiaUnderstanding)) == 1
        assert await session.scalar(select(func.count()).select_from(RockmamPossibilityAssessment)) == 1
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 2
        assert await session.scalar(select(func.count()).select_from(Inception)) == 0
        assert await session.scalar(select(func.count()).select_from(Mission)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionManifestation)) == 0
        assert await session.scalar(select(func.count()).select_from(AgentExecution)) == 0


@pytest.mark.asyncio
async def test_trinity_rejects_non_potential_without_side_effects(trinity_database):
    factory, ids = trinity_database
    path = f"/api/v1/trinity/god-interactions/{ids['direct']}/orchestrate"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        rejected = await client.post(path, headers=auth(ids["creator"]))
        assert rejected.status_code == 409
        assert rejected.json()["code"] == "TrinityError"

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(SophiaUnderstanding)) == 0
        assert await session.scalar(select(func.count()).select_from(RockmamPossibilityAssessment)) == 0
        assert await session.scalar(select(func.count()).select_from(Chronicle)) == 0
