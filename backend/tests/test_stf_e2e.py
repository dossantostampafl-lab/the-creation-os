"""End to end, chaos and security tests across Python (Authorization Plane) and the Rust gateway."""

import hashlib
import hmac

import httpx
import pytest
from stf_gateway_process import KEY, GatewayProcess, build_gateway
from stf_helpers import RANGE, action, make

from app.security_task_force.contracts import ActionRequest, AuthorizationDecision
from app.security_task_force.envelope import build_envelope, parameters_hash, signing_message
from app.security_task_force.evidence import EvidenceRecord
from app.security_task_force.gateway_client import GatewayUnavailable, TcpGatewayClient
from app.security_task_force.range_controller import RangeController, RangeRefused
from app.security_task_force.verification import verify_finding


@pytest.fixture(scope="module")
def binary():
    return build_gateway()


@pytest.fixture
def gateway(binary, tmp_path):
    process = GatewayProcess(binary, tmp_path / "gw").start()
    yield process
    process.stop()


def signed_parts(request: dict, tmp_path, *, nonce="n-1"):
    """An envelope the Authorization Plane would sign, built by hand for attack scenarios."""
    activities, deps = make(tmp_path)
    req = ActionRequest(**request)
    grant = deps.grants.issue(req)
    decision = AuthorizationDecision(decision_id="d", action_id=req.action_id, decision="permit", policy_version="stf-v1",
                                     environment_id=req.environment_id, capability_grant_reference=grant.grant_id)
    return req, build_envelope(req, decision, grant, key=KEY.encode(), nonce=nonce)


def requested_for(req: ActionRequest) -> dict:
    return {"mission_version": req.mission_version, "target": req.target_id, "environment": req.environment_id,
            "capability": req.capability, "action_class": req.action_class,
            "parameters_hash": parameters_hash(req.parameters), "tool_id": req.capability, "args_json": "{}"}


async def test_the_real_gateway_authorizes_but_executes_nothing_until_a_runtime_is_connected(gateway, tmp_path):
    """Python authorization -> signed envelope -> the real Rust gateway. The adapters are not connected to an
    isolation runtime, so the honest end of this chain is "authorized", never "executed"."""
    activities, deps = make(tmp_path, gateway=TcpGatewayClient("127.0.0.1", gateway.port))
    decision = await activities.authorize_action("m1", action(), None)
    result = await activities.dispatch_action(action(), decision)
    assert result["status"] == "authorized" and result["status"] != "executed"
    assert "execution_id" not in result and result["reasons"] == ["ExecutionNotImplemented"]
    # And the workflow's verification cannot complete a run that nothing proved.
    assert await activities.verify_mission("m1") is True  # only because this double declares it; see below
    deps.verify = None
    assert await activities.verify_mission("m1") is False


async def test_finding_verification_needs_correlated_intact_evidence():
    recorded = []

    def range_api(request: httpx.Request) -> httpx.Response:
        recorded.append(request.url.path)
        return httpx.Response(201, json={"evidence_id": "range-ev-1"})

    range_client = RangeController(transport=httpx.MockTransport(range_api))
    evidence_id = await range_client.record_evidence(RANGE, "juice-shop-xss", "attack", {"ok": True})
    attack = EvidenceRecord.build(evidence_id=evidence_id, mission_id="m1", action_id="a1", environment_id=RANGE,
                                  source="range", acquired_at="now", payload={"ok": True})
    defense = EvidenceRecord.build(evidence_id="d1", mission_id="m1", action_id="a1", environment_id=RANGE,
                                   source="range", acquired_at="now", payload={"alert": True}, kind="defense")
    verdict = verify_finding(attack, defense, purple_required=True, reproduced=True,
                             mission_id="m1", action_id="a1", environment_id=RANGE)
    assert verdict.status == "confirmed" and recorded == ["/evidence"]
    assert attack.chronicle_payload()["environment_id"] == RANGE
    # Evidence for another action never confirms this one.
    other = EvidenceRecord.build(evidence_id="e2", mission_id="m1", action_id="a-other", environment_id=RANGE,
                                 source="range", acquired_at="now", payload={"ok": True})
    assert verify_finding(other, defense, purple_required=True, reproduced=True, mission_id="m1", action_id="a1",
                          environment_id=RANGE).status == "rejected"


async def test_approval_gate_and_r5_never_execute_without_creator_or_new_mission(gateway, tmp_path):
    activities, deps = make(tmp_path, gateway=TcpGatewayClient("127.0.0.1", gateway.port))
    r3 = await activities.authorize_action("m1", action(risk_class="R3"), None)
    r5 = await activities.authorize_action("m1", action(risk_class="R5", action_id="a5"), "approval:1")
    assert r3["decision"] == "escalate" and r5["reasons"] == ["new_mission_required"]
    assert deps.grants._state()["grants"] == {}  # neither escalation produced any authority


async def test_forged_environment_is_refused_by_the_gateway_itself(binary, tmp_path):
    process = GatewayProcess(binary, tmp_path / "gw").start()
    try:
        _, deps = make(tmp_path)
        forged = ActionRequest(**action(environment_id="real:prod-a"))
        grant = deps.grants.issue(forged)
        decision = AuthorizationDecision(decision_id="d", action_id="a1", decision="permit", policy_version="stf-v1",
                                         environment_id="real:prod-a", capability_grant_reference=grant.grant_id)
        envelope = build_envelope(forged, decision, grant, key=KEY.encode(), nonce="forged")
        answer = await TcpGatewayClient("127.0.0.1", process.port).execute(envelope, requested_for(forged))
        assert answer["decision"] == "deny" and answer["reasons"] == ["EnvironmentNotAllowed"]
    finally:
        process.stop()


async def test_replay_tamper_and_parameter_swap_are_denied(gateway, tmp_path):
    client = TcpGatewayClient("127.0.0.1", gateway.port)
    req, envelope = signed_parts(action(), tmp_path)
    requested = requested_for(req)
    assert (await client.execute(envelope, requested))["decision"] == "permit"
    assert (await client.execute(envelope, requested))["reasons"] == ["Replay"]
    req2, envelope2 = signed_parts(action(action_id="a2"), tmp_path, nonce="n-2")
    swapped = {**requested_for(req2), "parameters_hash": parameters_hash({"path": "/admin"})}
    assert (await client.execute(envelope2, swapped))["reasons"] == ["ParametersTampered"]
    tampered = {**envelope2, "target": "another-target"}
    assert (await client.execute(tampered, requested_for(req2)))["reasons"] == ["BadSignature"]
    unsigned = {**envelope2, "signature": hmac.new(b"wrong-key", signing_message(envelope2).encode(), hashlib.sha256).hexdigest()}
    assert (await client.execute(unsigned, requested_for(req2)))["reasons"] == ["BadSignature"]


async def test_grant_for_one_target_cannot_be_used_for_another(tmp_path):
    activities, deps = make(tmp_path, gateway=None)
    decision = await activities.authorize_action("m1", action(), None)
    other = action(target_id="webgoat", idempotency_key="k-other")
    result = await activities.dispatch_action(other, decision)
    assert result["reasons"] == ["grant_invalid"] and deps.gateway.calls == []


async def test_gateway_restart_does_not_forget_spent_nonces(binary, tmp_path):
    state = tmp_path / "gw"
    first = GatewayProcess(binary, state).start()
    req, envelope = signed_parts(action(), tmp_path)
    assert (await TcpGatewayClient("127.0.0.1", first.port).execute(envelope, requested_for(req)))["decision"] == "permit"
    first.stop()
    second = GatewayProcess(binary, state).start()
    try:
        assert (await TcpGatewayClient("127.0.0.1", second.port).execute(envelope, requested_for(req)))["reasons"] == ["Replay"]
    finally:
        second.stop()


async def test_revocation_mid_task_and_gateway_outage_stop_execution(gateway, tmp_path):
    client = TcpGatewayClient("127.0.0.1", gateway.port)
    activities, deps = make(tmp_path, gateway=client)
    decision = await activities.authorize_action("m1", action(), None)
    await activities.revoke_grants("m1")  # also tells the gateway to kill the mission
    req, envelope = signed_parts(action(action_id="a9"), tmp_path, nonce="after-kill")
    assert (await client.execute(envelope, requested_for(req)))["reasons"] == ["KillSwitch"]
    assert (await activities.dispatch_action(action(), decision))["reasons"] == ["kill_switch"]
    gateway.stop()
    with pytest.raises(GatewayUnavailable):
        await client.execute(envelope, requested_for(req))


async def test_no_isolated_sandbox_means_a_permit_still_never_runs(binary, tmp_path):
    process = GatewayProcess(binary, tmp_path / "gw", kata=False).start()
    try:
        req, envelope = signed_parts(action(), tmp_path)
        answer = await TcpGatewayClient("127.0.0.1", process.port).execute(envelope, requested_for(req))
        assert answer["decision"] == "deny" and answer["reasons"] == ["SandboxUnavailable"]
    finally:
        process.stop()


async def test_range_client_refuses_real_environments_and_path_tricks():
    client = RangeController(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"scenarios": []})))
    with pytest.raises(RangeRefused):
        await client.start("real:prod-a", "juice-shop-xss")
    with pytest.raises(RangeRefused):
        await client.start(RANGE, "../reset")
