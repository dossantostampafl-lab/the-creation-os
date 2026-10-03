from datetime import datetime, timedelta, timezone

import httpx
import pytest
from stf_helpers import RANGE, FakeGateway, action, make

from app.security_task_force.contracts import ActionRequest
from app.security_task_force.grants import GrantStore
from app.security_task_force.policy import OpaClient


async def test_permitted_action_reaches_the_gateway_once_with_a_signed_envelope(tmp_path):
    activities, deps = make(tmp_path)
    decision = await activities.authorize_action("m1", action(), None)
    assert decision["decision"] == "permit"
    first = await activities.dispatch_action(action(), decision)
    again = await activities.dispatch_action(action(), decision)
    assert first == again == {"status": "executed", "execution_id": "exec-1", "reasons": []}
    assert len(deps.gateway.calls) == 1  # the duplicate key never repeats the external effect
    envelope, requested = deps.gateway.calls[0]
    assert envelope["environment"] == requested["environment"] == RANGE and len(envelope["signature"]) == 64


async def test_wrong_environment_is_denied_before_any_dispatch(tmp_path):
    activities, deps = make(tmp_path)
    decision = await activities.authorize_action("m1", action(environment_id="real:prod-a"), None)
    assert decision["decision"] == "deny" and decision["reasons"] == ["environment_not_authorized"]
    assert deps.gateway.calls == [] and deps.grants._state()["grants"] == {}


async def test_unknown_or_tampered_contract_denies(tmp_path):
    activities, deps = make(tmp_path)
    assert (await activities.authorize_action("nope", action(mission_id="nope"), None))["reasons"] == ["mission_unknown"]
    state = deps.contracts._state()
    state["m1"]["contract"]["authorized_targets"] = ["anything"]
    deps.contracts._memory = state
    deps.contracts._path = None
    assert (await activities.authorize_action("m1", action(), None))["reasons"] == ["mission_unknown"]


async def test_kill_switch_and_revocation_stop_dispatch(tmp_path):
    activities, deps = make(tmp_path)
    decision = await activities.authorize_action("m1", action(), None)
    await activities.revoke_grants("m1")
    assert deps.gateway.controls == [{"op": "kill", "mission_id": "m1"}]
    assert (await activities.dispatch_action(action(), decision))["reasons"] == ["kill_switch"]
    assert (await activities.authorize_action("m1", action(action_id="a2"), None))["reasons"] == ["kill_switch"]
    assert deps.gateway.calls == []


async def test_revoked_grant_alone_is_refused(tmp_path):
    activities, deps = make(tmp_path)
    decision = await activities.authorize_action("m1", action(), None)
    deps.grants.revoke(decision["grant_id"])
    result = await activities.dispatch_action(action(), decision)
    assert result["reasons"] == ["grant_invalid"] and deps.gateway.calls == []


async def test_gateway_outage_denies_and_a_crashed_dispatch_is_never_repeated(tmp_path):
    activities, deps = make(tmp_path, gateway=FakeGateway(fail=True))
    decision = await activities.authorize_action("m1", action(), None)
    assert (await activities.dispatch_action(action(), decision))["reasons"] == ["gateway_unavailable"]
    # A reservation with no completion (process died mid-dispatch) is unknown, not retried.
    assert deps.ledger.reserve("crash") == "reserved"
    assert (await activities.dispatch_action(action(idempotency_key="crash"), decision))["status"] == "unknown"


async def test_policy_outage_is_a_denial_and_a_policy_veto_is_honored(tmp_path):
    down = OpaClient("http://opa", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    activities, deps = make(tmp_path, policy=down)
    assert (await activities.authorize_action("m1", action(), None))["reasons"] == ["policy_unavailable"]
    veto = OpaClient("http://opa", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"result": {"allow": False, "reasons": ["target_not_authorized"]}})))
    activities, _ = make(tmp_path, policy=veto)
    assert (await activities.authorize_action("m1", action(), None))["reasons"] == ["target_not_authorized"]
    allow = OpaClient("http://opa", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"result": {"allow": True, "reasons": []}})))
    activities, _ = make(tmp_path, policy=allow)
    assert (await activities.authorize_action("m1", action(), None))["decision"] == "permit"


async def test_r3_escalates_until_the_creator_approves(tmp_path):
    activities, _ = make(tmp_path)
    risky = action(risk_class="R3")
    assert (await activities.authorize_action("m1", risky, None))["reasons"] == ["creator_approval_required"]
    assert (await activities.authorize_action("m1", risky, "approval:1"))["decision"] == "permit"


def test_grant_never_outlives_the_mission_window(tmp_path):
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    grant = GrantStore().issue(ActionRequest(**action()), not_after=soon)
    assert grant.expires_at == soon


@pytest.mark.parametrize("bad", [{"mission_id": ""}, {"environment_id": "prod"}, {"risk_class": "R9"}])
async def test_malformed_actions_are_rejected(tmp_path, bad):
    activities, _ = make(tmp_path)
    with pytest.raises(ValueError):
        await activities.authorize_action("m1", action(**bad), None)


# --- Task 1: no success without proof ---------------------------------------------------------

async def test_no_verifier_never_completes(tmp_path):
    from app.security_task_force.activities import StfActivities, StfDependencies
    from app.security_task_force.contract_store import ContractStore
    from app.security_task_force.grants import GrantStore
    from app.security_task_force.kill_switch import KillSwitch
    from app.security_task_force.ledger import DispatchLedger

    deps = StfDependencies(  # production shape: nobody supplied a verifier
        contracts=ContractStore(tmp_path / "c.json"), grants=GrantStore(tmp_path / "g.json"),
        kill_switch=KillSwitch(tmp_path / "k.json"), ledger=DispatchLedger(tmp_path / "l.json"),
        gateway=FakeGateway(), signing_key=b"k" * 40,
    )
    assert await StfActivities(deps).verify_mission("m1") is False


async def test_permit_is_not_execution(tmp_path):
    gateway = FakeGateway(answer={"decision": "permit", "status": "authorized", "reasons": ["ExecutionNotImplemented"]})
    activities, _ = make(tmp_path, gateway=gateway)
    decision = await activities.authorize_action("m1", action(), None)
    result = await activities.dispatch_action(action(), decision)
    assert result["status"] != "executed"
    assert result["status"] == "authorized"


async def test_executed_needs_an_execution_id(tmp_path):
    gateway = FakeGateway(answer={"decision": "permit", "status": "executed", "reasons": []})  # no execution_id
    activities, _ = make(tmp_path, gateway=gateway)
    decision = await activities.authorize_action("m1", action(), None)
    assert (await activities.dispatch_action(action(), decision))["status"] != "executed"


async def test_timeout_after_send_is_unknown(tmp_path):
    from app.security_task_force.gateway_client import GatewayOutcomeUnknown

    class LostAnswer(FakeGateway):
        async def execute(self, envelope, requested):
            self.calls.append((envelope, requested))  # the request left this process
            raise GatewayOutcomeUnknown("timeout waiting for the answer")

    gateway = LostAnswer()
    activities, deps = make(tmp_path, gateway=gateway)
    decision = await activities.authorize_action("m1", action(), None)
    result = await activities.dispatch_action(action(), decision)
    assert result["status"] == "unknown"
    # An unknown outcome is never sent a second time on its own.
    again = await activities.dispatch_action(action(), decision)
    assert again["status"] == "unknown" and len(gateway.calls) == 1


# --- Gauntlet Task 1: PostgreSQL is canonical authority for persisted runs ----------------------------

async def test_persisted_run_reserves_database_authority_before_gateway(stf_db, tmp_path):
    import uuid

    from app.models.entities import Creator
    from app.security_task_force.activities import StfActivities
    from app.security_task_force.contracts import CapabilityGrant
    from app.security_task_force.repository import StfRepository

    _, factory = stf_db
    creator_id, run_id, grant_id = str(uuid.uuid4()), str(uuid.uuid4()), f"grant:{uuid.uuid4()}"
    request = ActionRequest(**action())

    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"c-{creator_id[:8]}", password_hash="x", is_active=True))
        await session.flush()
        repository = StfRepository(session)
        await repository.create_run(
            creator_id=creator_id, run_id=run_id, mission_id=request.mission_id,
            mission_version=request.mission_version, request_key="gauntlet-1",
            request_hash="h" * 64, plan_hash="p" * 64, plan=[request.model_dump(mode="json")],
        )
        await repository.issue_grant(
            run_id,
            CapabilityGrant(
                grant_id=grant_id, mission_id=request.mission_id, mission_version=request.mission_version,
                actor=request.actor, capability=request.capability, target_id=request.target_id,
                environment_id=request.environment_id, action_class=request.action_class,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            ),
        )
        await session.commit()

    activities, deps = make(tmp_path)
    deps.session_factory = factory
    decision = {"decision": "permit", "decision_id": "d-db", "grant_id": grant_id}

    result = await activities.dispatch_action(action(), decision, run_id)

    assert result["status"] == "executed"
    assert len(deps.gateway.calls) == 1
    # A persisted run must not spend or reserve authority in the legacy file-backed stores.
    assert deps.grants.get(grant_id) is None
    assert deps.ledger.result(request.idempotency_key) is None

    async with factory() as session:
        row = (await session.execute(
            __import__("sqlalchemy").text(
                "SELECT status, grant_id FROM stf_dispatches WHERE run_id = :run_id AND action_id = :action_id"
            ),
            {"run_id": run_id, "action_id": request.action_id},
        )).one()
    assert tuple(row) == ("executed", grant_id)
