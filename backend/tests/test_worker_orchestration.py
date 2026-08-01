"""Lote 2.2 guardrail coverage: Mission status transitions driven by dispatch/lease/fail,
and the tail orchestration (consolidate -> decide -> manifest) that app/worker.py triggers.

Reuses the `consolidation_db` fixture from test_consolidation_integration.py (Mission
already EXECUTING with two fully-executed, consolidation-ready tasks) for the
orchestration guardrails, and a dedicated `undispatched_mission_db` fixture (mirroring
test_dispatch_integration.py's setup style) for the DISTRIBUTED/EXECUTING/FAILED
transitions, which need a mission that starts with nothing dispatched yet.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_consolidation_integration import consolidation_db  # noqa: F401  (reused fixture)

from app.config import settings
from app.core.domain import AuthorizationDenied
from app.db.session import get_session
from app.main import app
from app.models.consolidation import MissionConsolidation
from app.models.decision import MissionDecision
from app.models.entities import Agent, AgentCapability, Capability, Chronicle, Conversation, Creator, Inception, Message, Mission, Task
from app.models.manifestation import MissionManifestation
from app.repositories.consolidation import ConsolidationRepository
from app.repositories.decision import DecisionRepository
from app.repositories.manifestation import ManifestationRepository
from app.services.consolidation import ConsolidationError, ConsolidationService
from app.services.decision import DecisionService
from app.services.manifestation import ManifestationError, ManifestationService

pytestmark = pytest.mark.integration


def auth(subject: str) -> dict[str, str]:
    token = jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


async def mission_status(factory, mission_id: str) -> str:
    async with factory() as session:
        mission = await session.get(Mission, mission_id)
        return mission.status


@pytest.fixture
async def undispatched_mission_db():
    """A single-task, AUTHORIZED mission with nothing dispatched yet — for exercising
    the AUTHORIZED -> DISTRIBUTED -> EXECUTING -> FAILED transitions from scratch."""
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE dispatch_attempts, dispatch_items, task_dependencies, tasks, agent_capabilities, "
                "capabilities, agents, universes, chronicles, mission_plans, missions, inceptions, messages, "
                "conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    ids = {key: str(uuid.uuid4()) for key in ("creator", "conversation", "message", "inception", "mission", "capability", "agent", "task")}
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(Creator(id=ids["creator"], username="creator", password_hash="unused", is_active=True))
        await session.commit()
        session.add(Conversation(id=ids["conversation"], creator_id=ids["creator"], title="worker", status="active"))
        await session.commit()
        session.add(
            Message(
                id=ids["message"], conversation_id=ids["conversation"], role="creator", actor_id=ids["creator"],
                correlation_id=str(uuid.uuid4()), content="x", route="central", metadata_json={},
            )
        )
        await session.commit()
        session.add(
            Inception(
                id=ids["inception"], conversation_id=ids["conversation"], source_message_id=ids["message"],
                title="Worker", description="Worker orchestration", status="approved", trinity_assessment_json={},
            )
        )
        await session.commit()
        session.add(
            Mission(
                id=ids["mission"], inception_id=ids["inception"], creator_id=ids["creator"], title="Mission",
                objective="Exercise dispatch-driven status transitions", status="authorized", authorization_json={},
            )
        )
        session.add(Capability(id=ids["capability"], name="planning", description=""))
        session.add(
            Agent(
                id=ids["agent"], name="agent", description="", universe_name="central", active=True,
                capabilities_json={}, priority=1, status="idle", version=1, heartbeat_at=now, enabled=True,
            )
        )
        await session.commit()
        session.add(AgentCapability(agent_id=ids["agent"], capability_id=ids["capability"]))
        session.add(
            Task(
                id=ids["task"], mission_id=ids["mission"], name="Only", description="Only", required_capability_id=ids["capability"],
                priority=1, state="ready", retry_limit=1, retry_count=0, timeout_seconds=30, status="PENDING",
                input_json={}, output_json={}, error_json={}, attempt_count=0, max_attempts=1, idempotency_key=str(uuid.uuid4()),
            )
        )
        await session.commit()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield factory, ids
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_distributes_and_first_claim_executes_the_mission(undispatched_mission_db):
    """Guardrail 3 table: AUTHORIZED -> DISTRIBUTED on first enqueue, DISTRIBUTED ->
    EXECUTING on first successful claim/lease. Each transition emits a Chronicle."""
    factory, ids = undispatched_mission_db
    h = auth(ids["creator"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert await mission_status(factory, ids["mission"]) == "authorized"

        created = await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task"], "priority": 1, "max_attempts": 1})
        assert created.status_code == 201
        assert await mission_status(factory, ids["mission"]) == "distributed"

        leased = await c.post("/api/v1/dispatch/lease", headers=h, json={"worker_id": "w1", "lease_seconds": 60})
        assert leased.json()["item"] is not None
        assert await mission_status(factory, ids["mission"]) == "executing"

    async with factory() as session:
        types = set(
            (await session.scalars(select(Chronicle.event_type).where(Chronicle.aggregate_id == ids["mission"]))).all()
        )
    assert {"mission_distributed", "mission_executing"} <= types


@pytest.mark.asyncio
async def test_definitive_task_failure_fails_the_mission(undispatched_mission_db):
    """Guardrail 4: a task that exhausts max_attempts (dead-letters) fails the Mission,
    with a Chronicle event, and does so atomically (no error surfaced to the caller)."""
    factory, ids = undispatched_mission_db
    h = auth(ids["creator"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        created = await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task"], "priority": 1, "max_attempts": 1})
        item_id = created.json()["id"]
        leased = await c.post("/api/v1/dispatch/lease", headers=h, json={"worker_id": "w1", "lease_seconds": 60})
        token = leased.json()["lease_token"]
        assert await mission_status(factory, ids["mission"]) == "executing"

        failed = await c.post(
            f"/api/v1/dispatch/{item_id}/fail",
            headers=h,
            json={"worker_id": "w1", "lease_token": token, "error_code": "HANDLER_FAILED", "error_message": "no retries left"},
        )
        assert failed.status_code == 200
        assert failed.json()["state"] == "dead_lettered"

    assert await mission_status(factory, ids["mission"]) == "failed"
    async with factory() as session:
        event_types = (await session.scalars(select(Chronicle.event_type).where(Chronicle.aggregate_id == ids["mission"]))).all()
    assert "mission_failed" in set(event_types)


@pytest.mark.asyncio
async def test_tail_orchestration_never_runs_for_a_failed_mission(undispatched_mission_db):
    """Guardrail 4: once FAILED, consolidate/decide/manifest all refuse — this is the
    exact sequence app/worker.py's _try_close_out_mission attempts after every
    successful execution, so this proves it correctly declines for a failed Mission."""
    factory, ids = undispatched_mission_db
    h = auth(ids["creator"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        created = await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task"], "priority": 1, "max_attempts": 1})
        item_id = created.json()["id"]
        leased = await c.post("/api/v1/dispatch/lease", headers=h, json={"worker_id": "w1", "lease_seconds": 60})
        token = leased.json()["lease_token"]
        await c.post(
            f"/api/v1/dispatch/{item_id}/fail",
            headers=h,
            json={"worker_id": "w1", "lease_token": token, "error_code": "E", "error_message": "fail"},
        )
    assert await mission_status(factory, ids["mission"]) == "failed"

    async with factory() as session:
        with pytest.raises(AuthorizationDenied):
            await ConsolidationService(ConsolidationRepository(session)).consolidate(ids["mission"])
    async with factory() as session:
        with pytest.raises(AuthorizationDenied):
            await DecisionService(DecisionRepository(session)).decide(ids["mission"])
    async with factory() as session:
        with pytest.raises(AuthorizationDenied):
            await ManifestationService(ManifestationRepository(session)).manifest(ids["mission"])

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 0
        assert await session.scalar(select(func.count()).select_from(MissionManifestation)) == 0


async def _close_out_mission_once(factory, mission_id: str) -> str:
    """Mirrors app.worker._try_close_out_mission exactly: consolidate -> decide ->
    manifest, tolerating "not ready yet" / already-done races silently."""
    correlation_id = str(uuid.uuid4())
    try:
        async with factory() as session:
            consolidation, _ = await ConsolidationService(ConsolidationRepository(session)).consolidate(
                mission_id, correlation_id=correlation_id, actor_id="worker-under-test", actor_role="worker"
            )
    except (ConsolidationError, AuthorizationDenied):
        return "declined-at-consolidation"
    async with factory() as session:
        decision, _ = await DecisionService(DecisionRepository(session)).decide(
            mission_id, correlation_id=correlation_id, actor_id="worker-under-test", actor_role="worker",
            causation_id=consolidation.id,
        )
    async with factory() as session:
        try:
            await ManifestationService(ManifestationRepository(session)).manifest(
                mission_id, correlation_id=correlation_id, actor_id="worker-under-test", actor_role="worker",
                causation_id=decision.id,
            )
        except ManifestationError:
            return "declined-at-manifestation"
    return "manifested"


@pytest.mark.asyncio
async def test_concurrent_orchestration_produces_exactly_one_record_each(consolidation_db):  # noqa: F811
    """Guardrail 1: N concurrent close-out attempts for the same Mission (simulating the
    worker retrying after each of several tasks finishes near-simultaneously, or a
    restart mid-chain) must not duplicate any of the three tail records."""
    factory, ids = consolidation_db

    results = await asyncio.gather(*(_close_out_mission_once(factory, ids["mission"]) for _ in range(5)))
    assert all(result == "manifested" for result in results)

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 1
        assert await session.scalar(select(func.count()).select_from(MissionDecision)) == 1
        assert await session.scalar(select(func.count()).select_from(MissionManifestation)) == 1
    assert await mission_status(factory, ids["mission"]) == "manifested"


@pytest.mark.asyncio
async def test_manual_route_stays_idempotent_during_automatic_orchestration(consolidation_db):  # noqa: F811
    """Guardrail 2: the Creator's manual HTTP consolidate route and the worker's
    in-process orchestration converge on the same locked, idempotent path — racing them
    against the same Mission never produces more than one MissionConsolidation, and
    every response is either 201 (this call created it) or 200 (already existed)."""
    factory, ids = consolidation_db
    path = f"/api/v1/tree-core/missions/{ids['mission']}/consolidate"

    async def via_http():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(path, headers=auth(ids["creator"]))
            return response.status_code

    async def via_worker():
        async with factory() as session:
            _, created = await ConsolidationService(ConsolidationRepository(session)).consolidate(
                ids["mission"], correlation_id=str(uuid.uuid4()), actor_id="worker-under-test", actor_role="worker"
            )
            return 201 if created else 200

    results = await asyncio.gather(via_http(), via_worker(), via_http(), via_worker())
    assert set(results) <= {200, 201}
    assert results.count(201) == 1

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MissionConsolidation)) == 1
