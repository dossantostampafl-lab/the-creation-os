import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from test_dispatch_integration import auth

from app.main import app
from app.models.dispatch import DispatchItem, Worker
from app.repositories.dispatch import DispatchRepository
from app.repositories.tree_core import TreeCoreRepository
from app.repositories.workers import WorkerRepository
from app.services.dispatch import DispatchService
from app.services.tree_core import TreeCoreService
from app.services.workers import WorkerProtocolError, WorkerService

pytestmark = pytest.mark.integration
pytest_plugins = ["test_dispatch_integration"]


@pytest.fixture
async def worker_db(dispatch_db):
    factory, ids = dispatch_db
    async with factory() as session:
        await session.execute(text("TRUNCATE worker_capabilities, workers CASCADE"))
        await session.commit()
    return factory, ids


def worker_headers(worker_uuid, token):
    return {"X-Worker-UUID": worker_uuid, "X-Worker-Token": token}


@pytest.mark.asyncio
async def test_worker_http_protocol_registration_heartbeat_claim_release_fail_shutdown(worker_db):
    factory, ids = worker_db
    worker_uuid = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/workers")).status_code == 401
        registered = await client.post(
            "/api/v1/workers/register",
            headers=auth(ids["creator"]),
            json={"worker_uuid": worker_uuid, "worker_name": "worker-one", "version": "1.0", "capabilities": ["planning"]},
        )
        assert registered.status_code == 201
        token = registered.json()["worker_token"]
        assert token
        headers = worker_headers(worker_uuid, token)
        assert (await client.post("/api/v1/workers/heartbeat", json={"version": "1.0"})).status_code == 401
        heartbeat = await client.post("/api/v1/workers/heartbeat", headers=headers, json={"version": "1.1", "status": "available"})
        assert heartbeat.status_code == 200 and heartbeat.json()["status"] == "available"
        assert (await client.post("/api/v1/workers/claim", headers=headers, json={})).json() is None

        created = await client.post("/api/v1/dispatch", headers=auth(ids["creator"]), json={"task_id": ids["task1"]})
        assert created.status_code == 201
        envelope = await client.post("/api/v1/workers/claim", headers=headers, json={"lease_seconds": 60})
        assert envelope.status_code == 200
        body = envelope.json()
        assert body["task_id"] == ids["task1"] and body["capability"] == "planning" and body["lease_token"]
        assert (await client.post("/api/v1/workers/claim", headers=headers, json={})).status_code == 409
        released = await client.post(
            "/api/v1/workers/release", headers=headers, json={"dispatch_id": body["dispatch_id"], "lease_token": body["lease_token"]}
        )
        assert released.status_code == 200 and released.json()["status"] == "available"
        second = await client.post("/api/v1/workers/claim", headers=headers, json={})
        acknowledged = await client.post(
            "/api/v1/workers/acknowledge",
            headers=headers,
            json={"dispatch_id": second.json()["dispatch_id"], "lease_token": second.json()["lease_token"]},
        )
        assert acknowledged.status_code == 200 and acknowledged.json()["status"] == "available"
        assert (await client.post("/api/v1/dispatch", headers=auth(ids["creator"]), json={"task_id": ids["task2"]})).status_code == 201
        third = await client.post("/api/v1/workers/claim", headers=headers, json={})
        failed = await client.post(
            "/api/v1/workers/fail",
            headers=headers,
            json={"dispatch_id": third.json()["dispatch_id"], "lease_token": third.json()["lease_token"], "error_code": "SAFE"},
        )
        assert failed.status_code == 200 and failed.json()["status"] == "available"
        shutdown = await client.post("/api/v1/workers/shutdown", headers=headers)
        assert shutdown.status_code == 200 and shutdown.json()["status"] == "retired"
        assert (await client.post("/api/v1/workers/heartbeat", headers=headers, json={"version": "1.0"})).status_code == 403
        listing = await client.get("/api/v1/workers", headers=auth(ids["creator"]))
        worker_id = listing.json()[0]["id"]
        assert "worker_token" not in listing.text and (await client.get(f"/api/v1/workers/{worker_id}", headers=auth(ids["creator"]))).status_code == 200

    async with factory() as session:
        worker = await session.scalar(select(Worker).where(Worker.worker_uuid == worker_uuid))
        assert worker.credential_hash != token


@pytest.mark.asyncio
async def test_worker_security_version_capability_and_lease_ownership(worker_db):
    factory, ids = worker_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth(ids["creator"])
        bad_version = await client.post(
            "/api/v1/workers/register",
            headers=h,
            json={"worker_uuid": str(uuid.uuid4()), "worker_name": "bad", "version": "2.0", "capabilities": ["planning"]},
        )
        assert bad_version.status_code == 409
        unknown = await client.post(
            "/api/v1/workers/register",
            headers=h,
            json={"worker_uuid": str(uuid.uuid4()), "worker_name": "bad", "version": "1.0", "capabilities": ["unknown"]},
        )
        assert unknown.status_code == 409
        credentials = []
        for name in ("one", "two"):
            worker_uuid = str(uuid.uuid4())
            response = await client.post(
                "/api/v1/workers/register",
                headers=h,
                json={"worker_uuid": worker_uuid, "worker_name": name, "version": "1.0", "capabilities": ["planning"]},
            )
            credentials.append((worker_uuid, response.json()["worker_token"]))
            assert (await client.post("/api/v1/workers/heartbeat", headers=worker_headers(*credentials[-1]), json={"version": "1.0"})).status_code == 200
        await client.post("/api/v1/dispatch", headers=h, json={"task_id": ids["task1"]})
        envelope = (await client.post("/api/v1/workers/claim", headers=worker_headers(*credentials[0]), json={})).json()
        stolen = await client.post(
            "/api/v1/workers/release",
            headers=worker_headers(*credentials[1]),
            json={"dispatch_id": envelope["dispatch_id"], "lease_token": envelope["lease_token"]},
        )
        assert stolen.status_code == 409
        assert (await client.post("/api/v1/workers/heartbeat", headers=worker_headers(credentials[0][0], "invalid"), json={"version": "1.0"})).status_code == 403


@pytest.mark.asyncio
async def test_worker_states_and_concurrent_claims(worker_db):
    factory, ids = worker_db

    def make_service(session):
        dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        return WorkerService(WorkerRepository(session), dispatch)

    credentials = []
    async with factory() as session:
        service = make_service(session)
        for name in ("a", "b"):
            worker, token = await service.register(str(uuid.uuid4()), name, "1.0", ["planning"])
            await service.heartbeat(worker, "1.0", "available")
            credentials.append((worker.worker_uuid, token))
        await service.dispatch.enqueue(ids["creator"], ids["task1"], 2, 3)
        await service.dispatch.enqueue(ids["creator"], ids["task2"], 1, 3)

    async def claim(identity):
        async with factory() as session:
            service = make_service(session)
            worker = await service.authenticate(*identity)
            return await service.claim(worker, 60)

    results = await asyncio.gather(*(claim(x) for x in credentials))
    assert len({x[0].id for x in results}) == 2

    async with factory() as session:
        service = make_service(session)
        worker = await service.authenticate(*credentials[0])
        with pytest.raises(WorkerProtocolError, match="available"):
            await service.claim(worker, 60)
        worker.status = "offline"
        await service.repository.commit()
        with pytest.raises(WorkerProtocolError, match="available"):
            await service.claim(worker, 60)

    async with factory() as session:
        rows = list((await session.scalars(select(DispatchItem))).all())
        assert len(rows) == 2 and all(row.state == "leased" for row in rows)
