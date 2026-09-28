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
    assert first == again == {"status": "executed", "reasons": []}
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
