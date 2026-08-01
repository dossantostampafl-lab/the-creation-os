import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from test_dispatch_integration import auth

from app.agents.handlers import HandlerDefinition, HandlerRegistry, ObjectPayload, StructuredResult
from app.core.domain import AuthorizationDenied
from app.main import app
from app.models.dispatch import DispatchItem
from app.models.entities import Agent, Mission, Task
from app.models.execution import AgentExecution, AgentExecutionEvent
from app.repositories.dispatch import DispatchRepository
from app.repositories.execution import ExecutionRepository
from app.repositories.tree_core import TreeCoreRepository
from app.repositories.workers import WorkerRepository
from app.services.dispatch import DispatchService
from app.services.execution import AgentExecutionService, ExecutionError
from app.services.tree_core import TreeCoreService
from app.services.workers import WorkerService

pytestmark = pytest.mark.integration
pytest_plugins = ["test_dispatch_integration"]


@pytest.fixture
async def execution_db(dispatch_db):
    factory, ids = dispatch_db
    async with factory() as session:
        await session.execute(text("TRUNCATE agent_execution_events, agent_executions CASCADE"))
        await session.commit()
    return factory, ids


def worker_headers(worker_uuid, token):
    return {"X-Worker-UUID": worker_uuid, "X-Worker-Token": token}


def execution_service(session, registry=None):
    dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
    return AgentExecutionService(ExecutionRepository(session), dispatch, registry) if registry else AgentExecutionService(ExecutionRepository(session), dispatch)


@pytest.mark.asyncio
async def test_all_execution_http_endpoints_and_tree_core_result(execution_db):
    factory, ids = execution_db
    worker_uuid = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        creator = auth(ids["creator"])
        registered = await client.post(
            "/api/v1/workers/register",
            headers=creator,
            json={"worker_uuid": worker_uuid, "worker_name": "executor", "version": "1.0", "capabilities": ["planning"]},
        )
        worker_token = registered.json()["worker_token"]
        headers = worker_headers(worker_uuid, worker_token)
        await client.post("/api/v1/workers/heartbeat", headers=headers, json={"version": "1.0"})
        await client.post("/api/v1/dispatch", headers=creator, json={"task_id": ids["task1"]})
        envelope = (await client.post("/api/v1/workers/claim", headers=headers, json={})).json()
        invalid = await client.post(
            "/api/v1/agents/executions",
            headers=headers,
            json={
                "dispatch_id": envelope["dispatch_id"],
                "lease_token": envelope["lease_token"],
                "handler_name": "structured_echo",
                "handler_version": "1.0",
                "state": "succeeded",
                "command": "shell",
            },
        )
        assert invalid.status_code == 422
        created = await client.post(
            "/api/v1/agents/executions",
            headers=headers,
            json={
                "dispatch_id": envelope["dispatch_id"],
                "lease_token": envelope["lease_token"],
                "handler_name": "structured_echo",
                "handler_version": "1.0",
            },
        )
        assert created.status_code == 201
        execution_id = created.json()["id"]
        assert (await client.post("/api/v1/agents/executions", headers=headers, json={
            "dispatch_id": envelope["dispatch_id"], "lease_token": envelope["lease_token"],
            "handler_name": "structured_echo", "handler_version": "1.0"})).status_code == 409
        assert (await client.post(f"/api/v1/agents/executions/{execution_id}/accept", headers=headers, json={"lease_token": envelope["lease_token"]})).status_code == 200
        run = await client.post(
            f"/api/v1/agents/executions/{execution_id}/run", headers=headers, json={"lease_token": envelope["lease_token"]}
        )
        assert run.status_code == 200 and run.json()["state"] == "succeeded"
        assert (await client.get("/api/v1/agents/executions")).status_code == 401
        listing = await client.get("/api/v1/agents/executions", headers=creator)
        # len(...) == 1 alone would also pass on a 422 error body ({"detail": [...]}
        # has exactly one key) if this route were ever shadowed again by tree_core's
        # GET /agents/{agent_id} — assert the actual shape, not just a count that
        # happens to coincide. See docs/AUDIT_v0.5.md section 10 for the router-order
        # bug this masked until Lote 2.6 exercised the endpoint for real.
        assert listing.status_code == 200
        assert isinstance(listing.json(), list) and len(listing.json()) == 1
        assert listing.json()[0]["id"] == execution_id
        assert (await client.get(f"/api/v1/agents/executions/{execution_id}", headers=creator)).status_code == 200
        events = await client.get(f"/api/v1/agents/executions/{execution_id}/events", headers=creator)
        assert [event["event_type"] for event in events.json()] == [
            "execution_created", "execution_accepted", "execution_started", "execution_succeeded", "result_returned"
        ]
        result = await client.get(f"/api/v1/agents/executions/{execution_id}/result", headers=creator)
        assert result.status_code == 200 and result.json()["status"] == "succeeded"
        assert "lease_token" not in result.text and "credential" not in result.text
        assert (await client.post(f"/api/v1/agents/executions/{execution_id}/run", headers=headers, json={"lease_token": envelope["lease_token"]})).status_code == 409
        assert (await client.get("/api/v1/agents/executions/not-a-uuid", headers=creator)).status_code == 422

    async with factory() as session:
        item = await session.get(DispatchItem, envelope["dispatch_id"])
        task = await session.get(Task, ids["task1"])
        assert item.state == "acknowledged" and task.state == "ready"
        with pytest.raises(Exception, match="append-only"):
            await session.execute(
                text("UPDATE agent_execution_events SET event_type='execution_failed' WHERE execution_id=:id"),
                {"id": execution_id},
            )
        await session.rollback()
        with pytest.raises(Exception, match="immutable"):
            await session.execute(
                text("UPDATE agent_executions SET output_payload='{}' WHERE id=:id"), {"id": execution_id}
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_wrong_worker_handler_lease_and_cancel(execution_db):
    _, ids = execution_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        creator = auth(ids["creator"])
        credentials = []
        for name in ("owner", "other"):
            worker_uuid = str(uuid.uuid4())
            response = await client.post(
                "/api/v1/workers/register", headers=creator,
                json={"worker_uuid": worker_uuid, "worker_name": name, "version": "1.0", "capabilities": ["planning"]},
            )
            credentials.append((worker_uuid, response.json()["worker_token"]))
            await client.post("/api/v1/workers/heartbeat", headers=worker_headers(*credentials[-1]), json={"version": "1.0"})
        await client.post("/api/v1/dispatch", headers=creator, json={"task_id": ids["task1"]})
        envelope = (await client.post("/api/v1/workers/claim", headers=worker_headers(*credentials[0]), json={})).json()
        unknown = await client.post(
            "/api/v1/agents/executions", headers=worker_headers(*credentials[0]),
            json={"dispatch_id": envelope["dispatch_id"], "lease_token": envelope["lease_token"], "handler_name": "missing", "handler_version": "1"},
        )
        assert unknown.status_code == 409
        stolen = await client.post(
            "/api/v1/agents/executions", headers=worker_headers(*credentials[1]),
            json={"dispatch_id": envelope["dispatch_id"], "lease_token": envelope["lease_token"], "handler_name": "structured_echo", "handler_version": "1.0"},
        )
        assert stolen.status_code == 409
        created = await client.post(
            "/api/v1/agents/executions", headers=worker_headers(*credentials[0]),
            json={"dispatch_id": envelope["dispatch_id"], "lease_token": envelope["lease_token"], "handler_name": "structured_echo", "handler_version": "1.0"},
        )
        execution_id = created.json()["id"]
        cancelled = await client.post(
            f"/api/v1/agents/executions/{execution_id}/cancel",
            headers=worker_headers(*credentials[0]), json={"lease_token": envelope["lease_token"]},
        )
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
        assert (await client.get(f"/api/v1/agents/executions/{execution_id}/result", headers=creator)).json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_timeout_failure_and_concurrent_replay(execution_db):
    factory, ids = execution_db

    async def slow(_, payload):
        await asyncio.sleep(2)
        return {"status": "succeeded", "output": payload, "metrics": {}, "warnings": [], "error": None}

    registry = HandlerRegistry(
        [HandlerDefinition("slow", "1", "planning", ObjectPayload, StructuredResult, 1, True, "none", slow)]
    )
    async with factory() as session:
        workers = WorkerService(
            WorkerRepository(session), DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        )
        worker, worker_token = await workers.register(str(uuid.uuid4()), "slow", "1.0", ["planning"])
        await workers.heartbeat(worker, "1.0", "available")
        await workers.dispatch.enqueue(ids["creator"], ids["task1"], 0, 3)
        claimed = await workers.claim(worker, 60)
        item, lease_token, _ = claimed
        service = execution_service(session, registry)
        execution = await service.create(worker, item.id, lease_token, "slow", "1")
        await service.accept(execution.id, worker, lease_token)
        timed_out = await service.run(execution.id, worker, lease_token)
        assert timed_out.state == "timed_out" and timed_out.error_code == "EXECUTION_TIMEOUT"

    async with factory() as session:
        events = list((await session.scalars(select(AgentExecutionEvent).where(AgentExecutionEvent.execution_id == execution.id))).all())
        assert {event.event_type for event in events} >= {"execution_timed_out", "result_returned"}
        persisted = await session.get(AgentExecution, execution.id)
        assert persisted.output_payload is None

    async with factory() as session:
        workers = WorkerService(
            WorkerRepository(session), DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        )
        worker = await workers.authenticate(worker.worker_uuid, worker_token)
        item = await session.get(DispatchItem, item.id)
        item.available_at = datetime.now(timezone.utc)
        await session.commit()
        claimed = await workers.claim(worker, 60)
        item, lease_token, _ = claimed

    async def create_once():
        async with factory() as session:
            workers = WorkerService(
                WorkerRepository(session), DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
            )
            current = await workers.authenticate(worker.worker_uuid, worker_token)
            try:
                value = await execution_service(session).create(current, item.id, lease_token, "structured_echo", "1.0")
                return value.id
            except ExecutionError:
                return "conflict"

    outcomes = await asyncio.gather(create_once(), create_once())
    assert outcomes.count("conflict") == 1


@pytest.mark.asyncio
async def test_authorization_chain_invalid_output_and_non_terminal_result(execution_db):
    factory, ids = execution_db

    async def invalid_output(_, payload):
        return {"payload": payload}

    registry = HandlerRegistry(
        [HandlerDefinition("invalid", "1", "planning", ObjectPayload, StructuredResult, 2, True, "none", invalid_output)]
    )
    async with factory() as session:
        workers = WorkerService(
            WorkerRepository(session), DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        )
        worker, _ = await workers.register(str(uuid.uuid4()), "invalid", "1.0", ["planning"])
        await workers.heartbeat(worker, "1.0", "available")
        await workers.dispatch.enqueue(ids["creator"], ids["task1"], 0, 3)
        item, lease_token, _ = await workers.claim(worker, 60)
        service = execution_service(session, registry)
        mission = await session.get(Mission, ids["mission"])
        mission.status = "validated"
        await session.commit()
        with pytest.raises(AuthorizationDenied, match="Mission"):
            await service.create(worker, item.id, lease_token, "invalid", "1")
        mission.status = "authorized"
        agent = await session.get(Agent, ids["agent"])
        agent.status = "busy"
        await session.commit()
        with pytest.raises(AuthorizationDenied, match="Agent"):
            await service.create(worker, item.id, lease_token, "invalid", "1")
        agent.status = "idle"
        await session.commit()
        execution = await service.create(worker, item.id, lease_token, "invalid", "1")
        with pytest.raises(ExecutionError, match="not terminal"):
            await service.result(execution.id)
        await service.accept(execution.id, worker, lease_token)
        failed = await service.run(execution.id, worker, lease_token)
        assert failed.state == "failed" and failed.error_code == "HANDLER_FAILED" and failed.output_payload is None
        with pytest.raises(Exception, match="not found"):
            await service.get(str(uuid.uuid4()))
