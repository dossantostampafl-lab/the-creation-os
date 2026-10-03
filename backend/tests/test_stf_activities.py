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

async def test_persisted_run_reserves_database_authority_before_gateway(tmp_path, monkeypatch):
    from app.security_task_force.runtime_contracts import DispatchReceipt

    activities, deps = make(tmp_path)
    calls = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def commit(self):
            calls.append(("commit",))

    class Repository:
        def __init__(self, session):
            self.session = session

        async def reserve_dispatch(self, run_id, request, grant_id):
            calls.append(("reserve", run_id, request.action_id, grant_id))
            return DispatchReceipt("authorized", "claim-1", [])

        async def record_evidence(self, run_id, execution_id, evidence):
            calls.append(("evidence", run_id, execution_id, evidence.evidence_id))

        async def record_outcome(self, execution_id, status, reason_codes=None, evidence_id=None):
            calls.append(("outcome", execution_id, status, tuple(reason_codes or [])))

        async def get_grant(self, grant_id, run_id=None):
            return deps.grants.get(grant_id)

    def factory():
        return Session()

    monkeypatch.setattr("app.security_task_force.repository.StfRepository", Repository)
    deps.session_factory = factory
    decision = await activities.authorize_action("m1", action(), None)

    result = await activities.dispatch_action(action(), decision, "run-1")

    assert result == {"status": "executed", "execution_id": "exec-1", "reasons": []}
    assert calls[0][:4] == ("reserve", "run-1", "a1", decision["grant_id"])
    assert ("outcome", "claim-1", "executed", ()) in calls
    assert len(deps.gateway.calls) == 1
    # Persisted runs must not reserve dispatch in the legacy file-backed ledger.
    assert deps.ledger.result("k1") is None


async def test_persisted_run_authorization_uses_database_contract_and_grant(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.security_task_force.contract_store import ContractStore
    from app.security_task_force.mission_compiler import compile_verified_contract

    activities, deps = make(tmp_path)
    deps.contracts = ContractStore(tmp_path / "empty-contracts.json")
    persisted = compile_verified_contract(
        intent="validate", candidate={
            "mission_id": "m1", "creator_id": "c1", "success_criteria": ["evidence"],
            "authorized_targets": ["juice-shop"], "allowed_action_classes": ["validate"], "risk_ceiling": "R4",
        }, authorized_environments=[RANGE],
    ).contract
    assert persisted is not None
    issued = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def commit(self):
            return None

    class Repository:
        def __init__(self, session):
            self.session = session

        async def get_run(self, run_id, *, lock=False):
            return SimpleNamespace(
                id=run_id, creator_id="c1", mission_id="m1", mission_version=1,
                desired_state="RUN", state="RUNNING",
            )

        async def get_contract(self, creator_id, mission_id, version=None):
            return SimpleNamespace(contract_json=persisted.model_dump(mode="json"))

        async def issue_grant(self, run_id, grant):
            issued.append((run_id, grant))
            return True

    monkeypatch.setattr("app.security_task_force.repository.StfRepository", Repository)
    deps.session_factory = lambda: Session()

    decision = await activities.authorize_action("m1", action(), None, "run-1")

    assert decision["decision"] == "permit"
    assert issued and issued[0][0] == "run-1" and issued[0][1].grant_id == decision["grant_id"]
    assert deps.grants._state()["grants"] == {}


async def test_persisted_dispatch_denial_never_reaches_gateway(tmp_path, monkeypatch):
    from app.security_task_force.runtime_contracts import DispatchReceipt

    activities, deps = make(tmp_path)
    decision = await activities.authorize_action("m1", action(), None)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def commit(self):
            return None

    class Repository:
        def __init__(self, session):
            self.session = session

        async def reserve_dispatch(self, run_id, request, grant_id):
            return DispatchReceipt("denied", None, ["run_cancelled"])

    monkeypatch.setattr("app.security_task_force.repository.StfRepository", Repository)
    deps.session_factory = lambda: Session()

    result = await activities.dispatch_action(action(), decision, "run-cancelled")

    assert result == {"status": "denied", "reasons": ["run_cancelled"]}
    assert deps.gateway.calls == []
    assert deps.ledger.result("k1") is None


async def test_persisted_lost_gateway_response_is_unknown_and_not_replayed(tmp_path, monkeypatch):
    from app.security_task_force.gateway_client import GatewayOutcomeUnknown
    from app.security_task_force.runtime_contracts import DispatchReceipt

    class LostAnswer(FakeGateway):
        async def execute(self, envelope, requested):
            self.calls.append((envelope, requested))
            raise GatewayOutcomeUnknown("answer lost")

    activities, deps = make(tmp_path, gateway=LostAnswer())
    decision = await activities.authorize_action("m1", action(), None)
    calls = []
    outcome = {"status": None}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def commit(self):
            return None

    class Repository:
        def __init__(self, session):
            self.session = session

        async def reserve_dispatch(self, run_id, request, grant_id):
            calls.append(("reserve", run_id, request.action_id, grant_id))
            if outcome["status"] is not None:
                return DispatchReceipt(outcome["status"], "claim-lost", ["gateway_response_lost"])
            return DispatchReceipt("authorized", "claim-lost", [])

        async def get_grant(self, grant_id, run_id=None):
            return deps.grants.get(grant_id)

        async def record_outcome(self, execution_id, status, reason_codes=None, evidence_id=None):
            outcome["status"] = status
            calls.append(("outcome", execution_id, status, tuple(reason_codes or [])))

    monkeypatch.setattr("app.security_task_force.repository.StfRepository", Repository)
    deps.session_factory = lambda: Session()

    first = await activities.dispatch_action(action(), decision, "run-1")
    second = await activities.dispatch_action(action(), decision, "run-1")

    assert first["status"] == second["status"] == "unknown"
    assert len(deps.gateway.calls) == 1
    assert ("outcome", "claim-lost", "unknown", ("gateway_response_lost",)) in calls
    assert deps.ledger.result("k1") is None


async def test_persisted_range_cancel_kills_before_cleanup(tmp_path, monkeypatch):
    from types import SimpleNamespace

    activities, deps = make(tmp_path)
    calls = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def commit(self):
            calls.append(("commit",))

    class Repository:
        def __init__(self, session):
            self.session = session

        async def get_run(self, run_id, *, lock=False):
            return SimpleNamespace(plan_json=[{"environment_id": RANGE}])

        async def revoke_run(self, run_id):
            calls.append(("revoke", run_id))

    monkeypatch.setattr("app.security_task_force.repository.StfRepository", Repository)
    deps.session_factory = lambda: Session()

    await activities.revoke_grants("m1", "run-1")

    assert deps.gateway.controls == [
        {"op": "kill", "mission_id": "m1"},
        {"op": "range_reset"},
    ]
    assert calls[0] == ("revoke", "run-1")


async def test_persisted_verifier_uses_database_evidence(tmp_path, monkeypatch):
    activities, deps = make(tmp_path, verify=lambda mission_id: False)
    calls = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class Repository:
        def __init__(self, session):
            self.session = session

        async def verify_run_evidence(self, run_id):
            calls.append(run_id)
            return True

    monkeypatch.setattr("app.security_task_force.repository.StfRepository", Repository)
    deps.session_factory = lambda: Session()

    assert await activities.verify_mission("m1", "run-1") is True
    assert calls == ["run-1"]
