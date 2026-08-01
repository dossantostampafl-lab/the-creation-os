import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.dispatch import DispatchItem
from app.models.entities import Agent, Capability, Conversation, Creator, Inception, Message, Mission, Task
from app.repositories.dispatch import DispatchRepository
from app.repositories.tree_core import TreeCoreRepository
from app.services.dispatch import DispatchError, DispatchService
from app.services.tree_core import TreeCoreService

pytestmark = pytest.mark.integration


def auth(subject):
    token = jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def dispatch_db():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.execute(
            text(
                "TRUNCATE dispatch_attempts, dispatch_items, task_dependencies, tasks, agent_capabilities, capabilities, agents, universes, chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    ids = {
        key: str(uuid.uuid4())
        for key in ("creator", "conversation", "message", "inception", "mission", "capability", "agent", "task1", "task2")
    }
    async with factory() as s:
        s.add(Creator(id=ids["creator"], username="creator", password_hash="unused", is_active=True))
        await s.commit()
        s.add(Conversation(id=ids["conversation"], creator_id=ids["creator"], title="dispatch", status="active"))
        await s.commit()
        s.add(
            Message(
                id=ids["message"],
                conversation_id=ids["conversation"],
                role="creator",
                actor_id=ids["creator"],
                correlation_id=str(uuid.uuid4()),
                content="x",
                route="central",
                metadata_json={},
            )
        )
        await s.commit()
        s.add(
            Inception(
                id=ids["inception"],
                conversation_id=ids["conversation"],
                source_message_id=ids["message"],
                title="i",
                description="d",
                status="approved",
                trinity_assessment_json={},
            )
        )
        await s.commit()
        s.add(
            Mission(
                id=ids["mission"],
                inception_id=ids["inception"],
                creator_id=ids["creator"],
                title="m",
                objective="o",
                status="authorized",
                authorization_json={},
            )
        )
        await s.commit()
        capability = Capability(id=ids["capability"], name="planning", description="")
        agent = Agent(
            id=ids["agent"],
            name="agent",
            description="",
            universe_name="central",
            priority=10,
            status="idle",
            version=1,
            heartbeat_at=datetime.now(timezone.utc),
            enabled=True,
            active=True,
            capabilities_json={},
        )
        agent.capabilities = [capability]
        s.add(agent)
        await s.commit()
        for key, name in (("task1", "one"), ("task2", "two")):
            s.add(
                Task(
                    id=ids[key],
                    mission_id=ids["mission"],
                    name=name,
                    description="d",
                    required_capability_id=ids["capability"],
                    priority=1,
                    state="ready",
                    retry_limit=3,
                    retry_count=0,
                    timeout_seconds=30,
                    status="PENDING",
                    input_json={},
                    output_json={},
                    error_json={},
                    attempt_count=0,
                    max_attempts=3,
                    idempotency_key=str(uuid.uuid4()),
                )
            )
        await s.commit()

    async def override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield factory, ids
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_all_dispatch_endpoints_retry_dead_letter_and_security(dispatch_db):
    factory, ids = dispatch_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/dispatch")).status_code == 401
        assert (await c.get("/api/v1/dispatch", headers=auth(str(uuid.uuid4())))).status_code == 403
        h = auth(ids["creator"])
        invalid = await c.post(
            "/api/v1/dispatch", headers=h, json={"task_id": ids["task1"], "state": "leased", "attempt_count": 9, "lease_token_hash": "x"}
        )
        assert invalid.status_code == 422
        created = await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task1"], "priority": 5, "max_attempts": 2})
        assert created.status_code == 201
        item_id = created.json()["id"]
        assert "lease_token_hash" not in created.json()
        assert (await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task1"]})).status_code == 409
        assert len((await c.get("/api/v1/dispatch?limit=1&offset=0&state=queued", headers=h)).json()) == 1
        assert (await c.get(f"/api/v1/dispatch/{item_id}", headers=h)).status_code == 200
        leased = await c.post("/api/v1/dispatch/lease", headers=h, json={"worker_id": "w1", "lease_seconds": 60})
        token = leased.json()["lease_token"]
        assert token and "lease_token_hash" not in leased.text
        assert (
            await c.post(
                f"/api/v1/dispatch/{item_id}/renew", headers=h, json={"worker_id": "w1", "lease_token": token, "lease_seconds": 120}
            )
        ).status_code == 200
        assert (
            await c.post(f"/api/v1/dispatch/{item_id}/release", headers=h, json={"worker_id": "w1", "lease_token": token})
        ).status_code == 200
        # Enqueue + cancel a second task while the Mission is still active (DISTRIBUTED at
        # this point). Done here, before task1 is driven to dead-letter below, because once
        # that happens the Mission goes FAILED and dispatch stops accepting new work for it
        # (Guardrail 4) — re-asserted with a fresh enqueue attempt at the end of this test.
        second = await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task2"]})
        second_id = second.json()["id"]
        assert (await c.post(f"/api/v1/dispatch/{second_id}/cancel", headers=h)).json()["state"] == "cancelled"
        leased2 = await c.post("/api/v1/dispatch/lease", headers=h, json={"worker_id": "w1", "lease_seconds": 60})
        token2 = leased2.json()["lease_token"]
        assert token2 != token
        failed = await c.post(
            f"/api/v1/dispatch/{item_id}/fail",
            headers=h,
            json={"worker_id": "w1", "lease_token": token2, "error_code": "E1", "error_message": "safe"},
        )
        assert failed.json()["state"] == "retry_scheduled"
        async with factory() as s:
            x = await s.get(DispatchItem, item_id)
            x.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await s.commit()
        leased3 = await c.post("/api/v1/dispatch/lease", headers=h, json={"worker_id": "w2", "lease_seconds": 60})
        token3 = leased3.json()["lease_token"]
        dead = await c.post(
            f"/api/v1/dispatch/{item_id}/fail", headers=h, json={"worker_id": "w2", "lease_token": token3, "error_code": "E2"}
        )
        assert dead.json()["state"] == "dead_lettered"
        attempts = await c.get(f"/api/v1/dispatch/{item_id}/attempts", headers=h)
        assert attempts.status_code == 200 and len(attempts.json()) >= 5 and "lease_token_hash" not in attempts.text
        # task1's definitive failure fails the Mission (Guardrail 4). task2 is still "ready"
        # (cancelling its earlier dispatch item above never touched Task.state), but dispatch
        # must now refuse any new work for this Mission.
        blocked = await c.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task2"]})
        assert blocked.status_code == 403
        assert (await c.get("/api/v1/dispatch/not-a-uuid", headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_concurrent_lease_and_enqueue(dispatch_db):
    factory, ids = dispatch_db
    async with factory() as s:
        service = DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s)))
        await service.enqueue(ids["creator"], ids["task1"], 1, 3)

    async def lease(worker):
        async with factory() as s:
            return await DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s))).lease(worker, 60)

    results = await asyncio.gather(lease("a"), lease("b"))
    assert sum(x[0] is not None for x in results) == 1

    async def enqueue():
        async with factory() as s:
            try:
                await DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s))).enqueue(
                    ids["creator"], ids["task2"], 1, 3
                )
                return "ok"
            except DispatchError:
                return "conflict"

    assert sorted(await asyncio.gather(enqueue(), enqueue())) == ["conflict", "ok"]
    async with factory() as s:
        assert len(list((await s.scalars(select(DispatchItem))).all())) == 2


@pytest.mark.asyncio
async def test_dispatch_error_paths_expiration_acknowledge_and_release(dispatch_db):
    factory, ids = dispatch_db
    async with factory() as s:
        service = DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s)))
        with pytest.raises(Exception, match="Task not found"):
            await service.enqueue(ids["creator"], str(uuid.uuid4()), 0, 3)
        task = await s.get(Task, ids["task1"])
        task.state = "planned"
        await s.commit()
        with pytest.raises(DispatchError, match="eligible"):
            await service.enqueue(ids["creator"], ids["task1"], 0, 3)
        task.state = "ready"
        await s.commit()
        item = await service.enqueue(ids["creator"], ids["task1"], 0, 3)
        _, token = await service.lease("worker", 60)
        with pytest.raises(DispatchError, match="Invalid lease"):
            await service.renew(item.id, "worker", "wrong-token-value-that-is-long", 60)
        await service.release(item.id, "worker", token)
        with pytest.raises(DispatchError):
            await service.release(item.id, "worker", token)
        _, token2 = await service.lease("worker", 60)
        assert (await service.acknowledge(item.id, "worker", token2)).state == "acknowledged"
        with pytest.raises(DispatchError):
            await service.acknowledge(item.id, "worker", token2)
        with pytest.raises(Exception):
            await service.cancel(item.id)
        assert (await service.lease("empty", 60))[0] is None
    async with factory() as s:
        service = DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s)))
        second = await service.enqueue(ids["creator"], ids["task2"], 0, 3)
        _, token = await service.lease("expiring", 60)
        second.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.commit()
        with pytest.raises(DispatchError, match="expired"):
            await service.fail(second.id, "expiring", token, "E", "x")
        recovered, new_token = await service.lease("new-worker", 60)
        assert recovered.id == second.id and new_token != token


@pytest.mark.asyncio
async def test_concurrent_terminal_transitions_multiple_leases_and_cancel_race(dispatch_db):
    factory, ids = dispatch_db
    async with factory() as s:
        service = DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s)))
        first = await service.enqueue(ids["creator"], ids["task1"], 2, 3)
        await service.enqueue(ids["creator"], ids["task2"], 1, 3)

    async def lease(worker):
        async with factory() as s:
            return await DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s))).lease(worker, 60)

    leased = await asyncio.gather(lease("one"), lease("two"))
    assert len({result[0].id for result in leased if result[0]}) == 2
    first_result = next(result for result in leased if result[0].id == first.id)
    token = first_result[1]

    async def terminal(kind):
        async with factory() as s:
            service = DispatchService(DispatchRepository(s), TreeCoreService(TreeCoreRepository(s)))
            try:
                if kind == "ack":
                    await service.acknowledge(first.id, first_result[0].lease_owner, token)
                else:
                    await service.fail(first.id, first_result[0].lease_owner, token, "E", "failure")
                return "ok"
            except DispatchError:
                return "conflict"

    assert sorted(await asyncio.gather(terminal("ack"), terminal("fail"))) == ["conflict", "ok"]
    async with factory() as s:
        persisted = await s.get(DispatchItem, first.id)
        assert persisted.state in {"acknowledged", "retry_scheduled"}
