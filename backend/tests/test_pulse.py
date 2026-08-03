"""Lote: logging JSON estruturado + métricas de observabilidade (Parte B).
Confirms each new Pulse field reflects real data — same pattern as the
rest of Pulse's own tests (test_god_integration.py's SYSTEM_QUERY/pulse
test): create real rows, read the real snapshot, compare.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import app
from app.models.entities import Agent, Capability, Conversation, Creator, Inception, Message, Mission, Task
from app.observability.metrics import request_metrics
from app.repositories.dispatch import DispatchRepository
from app.repositories.tree_core import TreeCoreRepository
from app.services.dispatch import DispatchService
from app.services.pulse import build_pulse_snapshot
from app.services.tree_core import TreeCoreService

pytestmark = pytest.mark.integration


async def _get_or_create_creator(session) -> str:
    creator = await session.scalar(select(Creator))
    if creator is None:
        creator = Creator(id=str(uuid.uuid4()), username=f"creator-{uuid.uuid4().hex[:8]}", password_hash="unused", is_active=True)
        session.add(creator)
        await session.commit()
    return creator.id


async def _create_inception(session, creator_id: str, *, status: str) -> str:
    conversation_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    inception_id = str(uuid.uuid4())
    session.add(Conversation(id=conversation_id, creator_id=creator_id, title="pulse test", status="active"))
    await session.commit()
    session.add(
        Message(
            id=message_id, conversation_id=conversation_id, role="creator", actor_id=creator_id,
            correlation_id=str(uuid.uuid4()), content="x", route="central", metadata_json={},
        )
    )
    await session.commit()
    session.add(
        Inception(
            id=inception_id, conversation_id=conversation_id, source_message_id=message_id,
            title="pulse test inception", description="d", status=status, trinity_assessment_json={},
        )
    )
    await session.commit()
    return inception_id


async def _create_mission(session, creator_id: str, inception_id: str, *, status: str = "drafted") -> str:
    mission_id = str(uuid.uuid4())
    session.add(
        Mission(
            id=mission_id, inception_id=inception_id, creator_id=creator_id,
            title="pulse test mission", objective="o", status=status, authorization_json={},
        )
    )
    await session.commit()
    return mission_id


@pytest.mark.asyncio
async def test_approved_inceptions_reflects_real_data():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            creator_id = await _get_or_create_creator(session)
            await _create_inception(session, creator_id, status="approved")
            baseline = (await build_pulse_snapshot(session))["approved_inceptions"]

        async with factory() as session:
            await _create_inception(session, creator_id, status="approved")
            await _create_inception(session, creator_id, status="proposed")  # must not count
            snapshot = await build_pulse_snapshot(session)
        assert snapshot["approved_inceptions"] == baseline + 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_total_missions_created_reflects_real_data():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            creator_id = await _get_or_create_creator(session)
            baseline = (await build_pulse_snapshot(session))["total_missions_created"]

        async with factory() as session:
            for status in ("drafted", "manifested", "failed"):  # every status counts — this is a total, not a filter
                inception_id = await _create_inception(session, creator_id, status="approved")
                await _create_mission(session, creator_id, inception_id, status=status)
            snapshot = await build_pulse_snapshot(session)
        assert snapshot["total_missions_created"] == baseline + 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dispatch_items_acknowledged_and_queue_depth_reflect_real_data():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            creator_id = await _get_or_create_creator(session)
            inception_id = await _create_inception(session, creator_id, status="approved")
            mission_id = await _create_mission(session, creator_id, inception_id, status="authorized")

            capability = Capability(id=str(uuid.uuid4()), name=f"pulse_test_{uuid.uuid4().hex[:8]}", description="pulse test")
            session.add(capability)
            await session.commit()

            agent = Agent(
                id=str(uuid.uuid4()), name=f"agent-{uuid.uuid4().hex[:8]}", description="", universe_name="central",
                priority=10, status="idle", version=1, heartbeat_at=datetime.now(timezone.utc),
                enabled=True, active=True, capabilities_json={},
            )
            agent.capabilities = [capability]
            session.add(agent)
            await session.commit()

            task_ids = []
            for index in range(2):
                task_id = str(uuid.uuid4())
                session.add(
                    Task(
                        id=task_id, mission_id=mission_id, name=f"task-{index}-{uuid.uuid4().hex[:6]}", description="d",
                        required_capability_id=capability.id, priority=1, state="ready",
                        retry_limit=3, retry_count=0, timeout_seconds=30, status="PENDING",
                        input_json={}, output_json={}, error_json={}, attempt_count=0,
                        max_attempts=3, idempotency_key=str(uuid.uuid4()),
                    )
                )
                await session.commit()
                task_ids.append(task_id)

            baseline = await build_pulse_snapshot(session)

        # Two fresh dispatch items, both start "queued" — queue depth grows
        # by 2, nothing acknowledged yet.
        async with factory() as session:
            dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
            await dispatch.enqueue(creator_id, task_ids[0], 0, 3)
            await dispatch.enqueue(creator_id, task_ids[1], 0, 3)
            after_enqueue = await build_pulse_snapshot(session)
        assert after_enqueue["dispatch_queue_depth"] == baseline["dispatch_queue_depth"] + 2
        assert after_enqueue["dispatch_items_acknowledged"] == baseline["dispatch_items_acknowledged"]

        # Lease one (moves it out of queue depth, still not acknowledged),
        # then acknowledge it (moves it into dispatch_items_acknowledged).
        # One item remains queued, untouched, throughout.
        async with factory() as session:
            dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
            leased_item, token = await dispatch.lease(f"pulse-test-worker-{uuid.uuid4().hex[:8]}", 60, [capability.id])
            assert leased_item is not None
            after_lease = await build_pulse_snapshot(session)
            await dispatch.acknowledge(leased_item.id, leased_item.lease_owner, token)
            after_ack = await build_pulse_snapshot(session)

        assert after_lease["dispatch_queue_depth"] == baseline["dispatch_queue_depth"] + 1
        assert after_ack["dispatch_queue_depth"] == baseline["dispatch_queue_depth"] + 1
        assert after_ack["dispatch_items_acknowledged"] == baseline["dispatch_items_acknowledged"] + 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_metrics_reflect_real_requests():
    before = request_metrics.snapshot()["http_requests_total"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            response = await client.get("/api/v1/health/live")
            assert response.status_code == 200
    after = request_metrics.snapshot()["http_requests_total"]
    assert after - before == 3


@pytest.mark.asyncio
async def test_pulse_response_schema_includes_new_fields_without_removing_old_ones():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            snapshot = await build_pulse_snapshot(session)
        existing_fields = {
            "status", "database", "redis", "redis_streams", "chronicles_chain", "active_universes",
            "active_agents", "running_missions", "pending_inceptions", "pending_tasks", "failed_tasks",
            "error_count", "timestamp",
        }
        new_fields = {
            "approved_inceptions", "total_missions_created", "dispatch_items_acknowledged",
            "dispatch_queue_depth", "http_requests_total", "http_errors_total", "http_average_latency_ms",
        }
        assert existing_fields <= set(snapshot)
        assert new_fields <= set(snapshot)
    finally:
        await engine.dispose()
