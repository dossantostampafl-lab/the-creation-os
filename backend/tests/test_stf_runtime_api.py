"""Explicit, authenticated, idempotent mission runs, against the guarded disposable database."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text

from app.api.security_task_force import get_adapter
from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.entities import Creator
from app.security_task_force.integration import build_adapter

RANGE = "cyber_range:lab-a"
BASE = "/api/v1/deus/security-missions"
CANDIDATE = {"mission_id": "m1", "success_criteria": ["evidence"], "allowed_action_classes": ["validate"], "risk_ceiling": "R4"}
COMPILE = {"intent": "validate the range", "candidate": CANDIDATE, "authorized_environments": [RANGE],
           "authorized_targets": ["juice-shop"]}
ACTION = dict(action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red", target_id="juice-shop",
              environment_id=RANGE, capability="range.health.verify", action_class="validate", risk_class="R2",
              idempotency_key="k1", parameters={"path": "/"})


@pytest.fixture
async def api(stf_db, tmp_path):
    _, factory = stf_db
    creator_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        session.add_all([Creator(id=creator_id, username="creator", password_hash="x", is_active=True),
                         Creator(id=other_id, username="other", password_hash="x", is_active=True)])
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    def headers(subject, key=None):
        token = jwt.encode({"sub": subject, "type": "access", "jti": str(uuid.uuid4()),
                            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                           settings.secret_key.get_secret_value(), algorithm="HS256")
        result = {"Authorization": f"Bearer {token}"}
        if key:
            result["Idempotency-Key"] = key
        return result

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_adapter] = lambda: build_adapter(tmp_path)
    previous = settings.sovereign_creator_id
    settings.sovereign_creator_id = creator_id
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, headers, creator_id, other_id, factory
    finally:
        settings.sovereign_creator_id = previous
        app.dependency_overrides.clear()


async def _count(factory, table):
    async with factory() as session:
        return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def _compiled(client, headers, creator_id):
    assert (await client.post(f"{BASE}/compile", headers=headers(creator_id), json=COMPILE)).status_code == 201


async def test_compiling_alone_queues_nothing(api):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    assert await _count(factory, "stf_runs") == 0 and await _count(factory, "stf_outbox") == 0
    assert await _count(factory, "stf_contracts") == 1


async def test_start_queues_one_run_and_repeats_are_idempotent(api):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    first = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "req-1"), json={"actions": [ACTION]})
    again = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "req-1"), json={"actions": [ACTION]})
    assert first.status_code == 202 and again.status_code == 202
    run = first.json()
    assert run["state"] == "QUEUED" and run["run_id"] == again.json()["run_id"]
    assert run["workflow_id"] == f"stf:{run['run_id']}"
    assert await _count(factory, "stf_runs") == 1 and await _count(factory, "stf_outbox") == 1
    fetched = await client.get(f"{BASE}/m1/runs/{run['run_id']}", headers=headers(creator_id))
    assert fetched.status_code == 200 and fetched.json()["state"] == "QUEUED"


async def test_same_key_with_different_content_is_a_conflict(api):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    assert (await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "req-1"), json={"actions": [ACTION]})).status_code == 202
    other = {**ACTION, "parameters": {"path": "/other"}}
    conflict = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "req-1"), json={"actions": [other]})
    assert conflict.status_code == 409
    assert await _count(factory, "stf_runs") == 1 and await _count(factory, "stf_outbox") == 1


async def test_a_missing_idempotency_key_is_refused(api):
    client, headers, creator_id, _, _ = api
    await _compiled(client, headers, creator_id)
    assert (await client.post(f"{BASE}/m1/runs", headers=headers(creator_id), json={"actions": [ACTION]})).status_code == 422


async def test_real_environments_are_forbidden(api):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    response = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "r"),
                                 json={"actions": [{**ACTION, "environment_id": "real:prod-a"}]})
    assert response.status_code == 403 and await _count(factory, "stf_runs") == 0


async def test_another_creator_gets_404_and_the_wrong_capability_is_refused(api):
    client, headers, creator_id, other_id, factory = api
    await _compiled(client, headers, creator_id)
    started = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "r"), json={"actions": [ACTION]})
    run_id = started.json()["run_id"]
    settings.sovereign_creator_id = other_id  # the other principal is now the sovereign; it still owns nothing here
    assert (await client.post(f"{BASE}/m1/runs", headers=headers(other_id, "r"), json={"actions": [ACTION]})).status_code == 404
    assert (await client.get(f"{BASE}/m1/runs/{run_id}", headers=headers(other_id))).status_code == 404
    settings.sovereign_creator_id = creator_id
    shell = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "r2"),
                              json={"actions": [{**ACTION, "capability": "shell.exec", "action_id": "a2", "idempotency_key": "k2"}]})
    assert shell.status_code == 422


@pytest.mark.parametrize("actions", [
    [],
    [{**ACTION, "mission_id": "other"}],
    [{**ACTION, "mission_version": 9}],
    [{**ACTION, "target_id": "webgoat"}],
    [{**ACTION, "action_class": "exploit"}],
    [ACTION, ACTION],
])
async def test_empty_or_incoherent_plans_are_422(api, actions):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    response = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "r"), json={"actions": actions})
    assert response.status_code == 422 and await _count(factory, "stf_runs") == 0


async def test_the_client_cannot_lower_the_risk_it_declares(api):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    started = await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "r"),
                                json={"actions": [{**ACTION, "risk_class": "R0"}]})
    assert started.status_code == 202
    async with factory() as session:
        plan = await session.scalar(text("SELECT plan_json FROM stf_runs"))
    assert plan[0]["risk_class"] == "R1"  # the diagnostic capability has one fixed class


async def test_approval_and_cancel_need_the_run_and_cancel_revokes(api):
    client, headers, creator_id, _, factory = api
    await _compiled(client, headers, creator_id)
    run_id = (await client.post(f"{BASE}/m1/runs", headers=headers(creator_id, "r"), json={"actions": [ACTION]})).json()["run_id"]
    assert (await client.post(f"{BASE}/m1/cancel", headers=headers(creator_id), json={"reason": "stop"})).status_code == 422
    assert (await client.post(f"{BASE}/m1/approval", headers=headers(creator_id),
                              json={"action_id": "a1", "decision": "approve"})).status_code == 422
    unknown_action = await client.post(f"{BASE}/m1/approval", headers=headers(creator_id),
                                       json={"run_id": run_id, "action_id": "zzz", "decision": "approve"})
    assert unknown_action.status_code == 422
    approved = await client.post(f"{BASE}/m1/approval", headers=headers(creator_id),
                                 json={"run_id": run_id, "action_id": "a1", "decision": "approve"})
    assert approved.status_code == 200 and await _count(factory, "stf_approvals") == 1
    cancelled = await client.post(f"{BASE}/m1/cancel", headers=headers(creator_id), json={"run_id": run_id, "reason": "stop"})
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "CANCELLING"
    late = await client.post(f"{BASE}/m1/approval", headers=headers(creator_id),
                             json={"run_id": run_id, "action_id": "a1", "decision": "approve"})
    assert late.status_code == 409  # a cancelling run takes no new approvals
    async with factory() as session:
        desired = await session.scalar(text("SELECT desired_state FROM stf_runs"))
    assert desired == "CANCEL"
