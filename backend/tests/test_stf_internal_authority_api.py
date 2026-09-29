"""Service-authenticated runtime claims: the gateway cannot execute from a Creator token alone."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import app
from app.models.entities import Creator
from app.security_task_force.canonicalize import canonical_hash
from app.security_task_force.contracts import ActionRequest, CapabilityGrant
from app.security_task_force.mission_compiler import compile_verified_contract
from app.security_task_force.repository import StfRepository

pytestmark = pytest.mark.integration
RANGE = "cyber_range:lab-a"
CLAIM = "/api/v1/deus/security-missions/internal/execution-claims"
TOKEN = "s" * 40


def action() -> ActionRequest:
    return ActionRequest(
        action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red",
        target_id="juice-shop", environment_id=RANGE, capability="range.health.verify",
        action_class="validate", risk_class="R1", idempotency_key="claim-k1", parameters={"path": "/"},
    )


async def seed(factory):
    creator_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
    request = action()
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"svc-{creator_id[:8]}", password_hash="x", is_active=True))
        await session.flush()
        compiled = compile_verified_contract(
            intent="validate",
            candidate={
                "mission_id": "m1", "creator_id": creator_id, "success_criteria": ["evidence"],
                "authorized_targets": ["juice-shop"], "allowed_action_classes": ["validate"], "risk_ceiling": "R4",
            },
            authorized_environments=[RANGE],
        )
        repository = StfRepository(session)
        await repository.save_contract(compiled)
        plan = [request.model_dump(mode="json")]
        await repository.create_run(
            creator_id=creator_id, run_id=run_id, mission_id="m1", mission_version=1,
            request_key="internal-claim", request_hash=canonical_hash(plan), plan_hash=canonical_hash(plan), plan=plan,
        )
        grant = CapabilityGrant(
            grant_id=f"grant:{uuid.uuid4()}", mission_id="m1", mission_version=1, actor=request.actor,
            capability=request.capability, target_id=request.target_id, environment_id=request.environment_id,
            action_class=request.action_class, expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            max_invocations=1,
        )
        await repository.issue_grant(run_id, grant)
        receipt = await repository.reserve_dispatch(run_id, request, grant.grant_id)
        contract = await repository.get_contract(creator_id, "m1", 1)
        await session.commit()
    assert receipt.execution_id and contract is not None
    return {
        "execution_id": receipt.execution_id,
        "run_id": run_id,
        "contract_hash": contract.contract_hash,
        "plan_hash": canonical_hash(plan),
        "tool_id": request.capability,
        "parameters_hash": canonical_hash(request.parameters),
    }


@pytest.fixture
async def client(stf_db):
    _, factory = stf_db

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
            yield value, factory
    finally:
        app.dependency_overrides.clear()


async def test_internal_claim_requires_a_configured_service_identity(client, monkeypatch):
    http, factory = client
    body = await seed(factory)
    monkeypatch.delenv("STF_AUTHORITY_SERVICE_TOKEN", raising=False)
    assert (await http.post(CLAIM, json=body)).status_code == 503


async def test_internal_claim_rejects_missing_or_wrong_service_identity(client, monkeypatch):
    http, factory = client
    body = await seed(factory)
    monkeypatch.setenv("STF_AUTHORITY_SERVICE_TOKEN", TOKEN)
    assert (await http.post(CLAIM, json=body)).status_code == 401
    assert (await http.post(CLAIM, headers={"X-STF-Service-Token": "wrong"}, json=body)).status_code == 401


async def test_internal_claim_commits_only_a_bound_persisted_authority(client, monkeypatch):
    http, factory = client
    body = await seed(factory)
    monkeypatch.setenv("STF_AUTHORITY_SERVICE_TOKEN", TOKEN)
    response = await http.post(CLAIM, headers={"X-STF-Service-Token": TOKEN}, json=body)
    assert response.status_code == 200
    assert response.json() == {"status": "dispatched", "execution_id": body["execution_id"], "reason_codes": []}


async def test_internal_claim_after_cancel_is_denied_without_resurrecting_the_run(client, monkeypatch):
    http, factory = client
    body = await seed(factory)
    monkeypatch.setenv("STF_AUTHORITY_SERVICE_TOKEN", TOKEN)
    async with factory() as session:
        await StfRepository(session).revoke_run(body["run_id"])
        await session.commit()
    response = await http.post(CLAIM, headers={"X-STF-Service-Token": TOKEN}, json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert "run_cancelled" in response.json()["reason_codes"]
