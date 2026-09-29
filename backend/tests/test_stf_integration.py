import inspect
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text

from app.api.security_task_force import get_adapter
from app.config import settings
from app.core.domain import Actor, AuthorizationDenied
from app.db.session import get_session
from app.main import app
from app.models.entities import Creator
from app.schemas.chronicle import ChronicleResponse
from app.security_task_force.integration import SecurityTaskForceAdapter, build_adapter

RANGE = "cyber_range:lab-a"
CANDIDATE = {"mission_id": "m1", "success_criteria": ["evidence"], "allowed_action_classes": ["validate"], "risk_ceiling": "R4"}
ACTION = dict(action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red", target_id="juice-shop",
              environment_id=RANGE, capability="range.health.verify", action_class="validate", risk_class="R2",
              idempotency_key="k1")


def adapter_for(tmp_path) -> SecurityTaskForceAdapter:
    return build_adapter(tmp_path)


def creator(subject="c1") -> Actor:
    return Actor(id=subject, role="creator")


def test_adapter_exposes_only_the_declared_boundary(tmp_path):
    public = {name for name, _ in inspect.getmembers(adapter_for(tmp_path), inspect.ismethod) if not name.startswith("_")}
    assert public == {"compile_mission", "request_authorization", "get_mission_status", "submit_creator_approval",
                      "cancel_mission", "get_verified_findings"}
    held = " ".join(vars(adapter_for(tmp_path))).lower()
    assert not any(word in held for word in ("session", "repository", "gateway", "executor", "sandbox"))


async def test_compile_authorize_status_cancel_flow(tmp_path):
    adapter = adapter_for(tmp_path)
    result = adapter.compile_mission(creator(), "validate the range", CANDIDATE, authorized_environments=[RANGE],
                                     authorized_targets=["juice-shop"])
    assert result.status == "COMPILED" and result.contract.creator_id == "c1"
    assert adapter.get_mission_status(creator(), "m1").status == "COMPILED"
    assert (await adapter.request_authorization(creator(), "m1", ACTION)).decision == "permit"
    assert (await adapter.request_authorization(creator(), "m1", {**ACTION, "environment_id": "real:prod-a"})).decision == "deny"
    with pytest.raises(ValueError):
        adapter.cancel_mission(creator(), "m1", "  ")
    adapter.cancel_mission(creator(), "m1", "creator changed their mind")
    assert adapter.get_mission_status(creator(), "m1").status == "ABORTED"
    assert (await adapter.request_authorization(creator(), "m1", {**ACTION, "action_id": "a2"})).reason_codes == ["kill_switch"]


async def test_another_creator_cannot_see_use_or_take_over_a_mission(tmp_path):
    adapter = adapter_for(tmp_path)
    adapter.compile_mission(creator(), "validate", CANDIDATE, authorized_environments=[RANGE], authorized_targets=["juice-shop"])
    for call in (lambda: adapter.get_mission_status(creator("other"), "m1"),
                 lambda: adapter.cancel_mission(creator("other"), "m1", "x"),
                 lambda: adapter.get_verified_findings(creator("other"), "m1")):
        with pytest.raises(LookupError):
            call()
    with pytest.raises(LookupError):
        await adapter.request_authorization(creator("other"), "m1", ACTION)
    with pytest.raises(AuthorizationDenied):
        adapter.compile_mission(creator("other"), "validate", CANDIDATE, authorized_environments=[RANGE],
                                authorized_targets=["juice-shop"])
    with pytest.raises(AuthorizationDenied):
        adapter.compile_mission(Actor(id="u", role="user"), "validate", CANDIDATE)


def test_creator_identity_comes_from_the_session_not_the_candidate(tmp_path):
    result = adapter_for(tmp_path).compile_mission(creator(), "validate", {**CANDIDATE, "creator_id": "spoofed"},
                                                   authorized_environments=[RANGE], authorized_targets=["juice-shop"])
    assert result.contract.creator_id == "c1"


def test_approval_needs_an_explicit_decision_and_only_approve_yields_a_reference(tmp_path):
    adapter = adapter_for(tmp_path)
    adapter.compile_mission(creator(), "validate", CANDIDATE, authorized_environments=[RANGE], authorized_targets=["juice-shop"])
    assert adapter.submit_creator_approval(creator(), "m1", "a1", "approve").startswith("creator-approval:c1:m1:a1")
    assert adapter.submit_creator_approval(creator(), "m1", "a1", "deny") is None
    with pytest.raises(ValueError):
        adapter.submit_creator_approval(creator(), "m1", "a1", "maybe")


def test_chronicle_response_surfaces_task_force_correlation():
    now = datetime.now(timezone.utc)
    base = dict(id="1", event_id="e", correlation_id="c", causation_id=None, actor_type="creator", actor_id="x",
                event_type="stf_action_decided", aggregate_type="stf_mission", aggregate_id="m1", payload_hash="h",
                previous_hash=None, created_at=now)
    item = ChronicleResponse(**base, payload_json={"mission_id": "m1", "environment_id": RANGE, "evidence_sha256": "ab"})
    assert (item.mission_id, item.environment_id, item.evidence_sha256) == ("m1", RANGE, "ab")
    assert ChronicleResponse(**base, payload_json={"x": 1}).mission_id is None


@pytest.mark.integration
async def test_http_routes_require_the_sovereign_creator_and_write_the_chronicle(tmp_path, stf_db):
    _, factory = stf_db  # the guarded disposable database, already emptied; never DATABASE_URL
    creator_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        session.add_all([Creator(id=creator_id, username="creator", password_hash="x", is_active=True),
                         Creator(id=other_id, username="other", password_hash="x", is_active=True)])
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    def headers(subject):
        token = jwt.encode({"sub": subject, "type": "access", "jti": str(uuid.uuid4()),
                            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                           settings.secret_key.get_secret_value(), algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_adapter] = lambda: build_adapter(tmp_path)
    previous = settings.sovereign_creator_id
    settings.sovereign_creator_id = creator_id
    body = {"intent": "validate the range", "candidate": CANDIDATE, "authorized_environments": [RANGE],
            "authorized_targets": ["juice-shop"]}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            base = "/api/v1/deus/security-missions"
            assert (await client.post(f"{base}/compile", json=body)).status_code in {401, 403}
            assert (await client.post(f"{base}/compile", json=body, headers=headers(other_id))).status_code in {401, 403}
            bad = await client.post(f"{base}/compile", headers=headers(creator_id), json={**body, "authorized_environments": []})
            assert bad.status_code == 422 and "environment" in bad.json()["detail"]["reason_codes"]
            ok = await client.post(f"{base}/compile", headers=headers(creator_id), json=body)
            assert ok.status_code == 201 and len(ok.json()["contract_hash"]) == 64
            decided = await client.post(f"{base}/m1/authorize", headers=headers(creator_id), json={"action": ACTION})
            assert decided.json()["decision"] == "permit"
            denied = await client.post(f"{base}/m1/authorize", headers=headers(creator_id),
                                       json={"action": {**ACTION, "action_id": "a2", "environment_id": "real:prod-a"}})
            assert denied.json()["reason_codes"] == ["environment_not_authorized"]
            assert (await client.get(f"{base}/m1", headers=headers(creator_id))).json()["status"] == "COMPILED"
            assert (await client.get(f"{base}/nope", headers=headers(creator_id))).status_code == 404
            assert (await client.post(f"{base}/m1/cancel", headers=headers(creator_id), json={"reason": "stop"})).json()["status"] == "ABORTED"
        async with factory() as session:
            events = (await session.execute(text("SELECT event_type FROM chronicles WHERE aggregate_type='stf_mission' ORDER BY position"))).scalars().all()
        assert events == ["stf_mission_compiled", "stf_action_decided", "stf_action_decided", "stf_mission_cancelled"]
    finally:
        settings.sovereign_creator_id = previous
        app.dependency_overrides.clear()


def test_required_policy_engine_is_never_bypassed(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("STF_REQUIRE_POLICY", "1")
    monkeypatch.delenv("OPA_URL", raising=False)
    with pytest.raises(HTTPException) as caught:
        get_adapter()
    assert caught.value.status_code == 503
    monkeypatch.setenv("OPA_URL", "http://stf-opa:8181")
    assert get_adapter() is not None
