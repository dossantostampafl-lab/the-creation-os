from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity

from .authorization import authorize_and_grant
from .contract_store import ContractStore
from .contracts import ActionRequest, AuthorizationDecision
from .envelope import build_envelope, parameters_hash
from .gateway_client import GatewayClient, GatewayOutcomeUnknown, GatewayUnavailable
from .grants import GrantStore
from .kill_switch import KillSwitch
from .ledger import DispatchLedger
from .policy import PolicyClient
from .status_store import MissionStatusStore
from .telemetry import emit


@dataclass
class StfDependencies:
    contracts: ContractStore
    grants: GrantStore
    kill_switch: KillSwitch
    ledger: DispatchLedger
    gateway: GatewayClient
    signing_key: bytes
    policy: PolicyClient | None = None
    # No default: a Mission is verified by something that checks evidence, or it is not verified at all.
    verify: Callable[[str], bool] | None = None
    states: list[tuple[str, str]] = field(default_factory=list)
    statuses: MissionStatusStore = field(default_factory=MissionStatusStore)
    # Short-lived database sessions for run state, approvals and cancellation; absent for file-only runs.
    session_factory: Callable[[], Any] | None = None


def receipt_from(answer: dict[str, Any]) -> dict[str, Any]:
    """What the gateway's answer proves. `permit` is authorization; only an execution id is execution."""
    reasons = [str(item) for item in answer.get("reasons", [])]
    if answer.get("decision") != "permit":
        return {"status": "denied", "reasons": reasons}
    status = answer.get("status")
    execution_id = answer.get("execution_id")
    if status == "executed" and isinstance(execution_id, str) and execution_id:
        return {"status": "executed", "execution_id": execution_id, "reasons": reasons}
    if status in ("authorized", "dispatched"):
        return {"status": status, "reasons": reasons}
    # An unrecognized answer to a permitted request (no status, or "executed" without proof) may hide
    # an effect, so it is unknown rather than either success or refusal.
    return {"status": "unknown", "reasons": [*reasons, "unproven_gateway_answer"]}


class StfActivities:
    """Every side effect of a Mission run. The workflow only orders these calls; each activity
    reloads the current contract, grant and kill-switch state itself, so a retry or a restart
    never acts on stale authority."""

    def __init__(self, deps: StfDependencies) -> None:
        self._d = deps

    @activity.defn(name="stf_authorize_action")
    async def authorize_action(self, mission_id: str, action: dict[str, Any], approval: str | None) -> dict[str, Any]:
        request = ActionRequest.model_validate(action)
        contract = self._d.contracts.get(mission_id)
        if contract is None:
            return {"decision": "deny", "reasons": ["mission_unknown"]}
        if not self._d.kill_switch.dispatch_allowed(mission_id):
            return {"decision": "deny", "reasons": ["kill_switch"]}
        decision = await authorize_and_grant(
            contract, request, grants=self._d.grants, policy=self._d.policy, creator_approval_reference=approval
        )
        emit("action.decided", mission_id=mission_id, action_id=request.action_id,
             environment_id=request.environment_id, decision=decision.decision, reasons=decision.reason_codes)
        return {"decision": decision.decision, "reasons": decision.reason_codes,
                "decision_id": decision.decision_id, "grant_id": decision.capability_grant_reference}

    @activity.defn(name="stf_check_approval")
    async def check_approval(self, run_id: str, approval_id: str, action: dict[str, Any]) -> bool:
        """The signal carries only an id. It unblocks the run only if that stored approval is for this run,
        this action and these exact parameters, unexpired and an approve. Anything else fails closed."""
        if not self._d.session_factory:
            return False
        from .repository import StfRepository

        async with self._d.session_factory() as session:
            return await StfRepository(session).approval_matches(approval_id, run_id, action)

    @activity.defn(name="stf_verify_mission")
    async def verify_mission(self, mission_id: str) -> bool:
        if self._d.verify is None:
            return False  # nothing can prove the run, so nothing completes
        return bool(self._d.verify(mission_id))

    @activity.defn(name="stf_record_state")
    async def record_state(self, mission_id: str, state: str, run_id: str | None = None) -> None:
        self._d.states.append((mission_id, state))
        if run_id and self._d.session_factory:
            from .repository import StfRepository

            async with self._d.session_factory() as session:
                await StfRepository(session).set_run_state(run_id, state)
                await session.commit()
        self._d.statuses.set_state(mission_id, state)
        emit("mission.state_changed", mission_id=mission_id, state=state)

    @activity.defn(name="stf_revoke_grants")
    async def revoke_grants(self, mission_id: str, run_id: str | None = None) -> int:
        """Stop new dispatch and expire every grant of the Mission before it reaches a terminal state."""
        if run_id and self._d.session_factory:
            from .repository import StfRepository

            async with self._d.session_factory() as session:
                await StfRepository(session).revoke_run(run_id)
                await session.commit()
        self._d.kill_switch.kill_mission(mission_id)
        count = self._d.grants.revoke_mission(mission_id)
        try:
            await self._d.gateway.control({"op": "kill", "mission_id": mission_id})
        except (GatewayUnavailable, GatewayOutcomeUnknown):
            pass  # the gateway also refuses on its own revocation state; this only tightens it sooner
        emit("grant.revoked", mission_id=mission_id, revoked=count)
        return count

    @activity.defn(name="stf_dispatch_action")
    async def dispatch_action(self, action: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        """Hand a permitted action to the gateway, at most once per idempotency key."""
        request = ActionRequest.model_validate(action)
        if not self._d.kill_switch.dispatch_allowed(request.mission_id):
            return {"status": "denied", "reasons": ["kill_switch"]}
        state = self._d.ledger.reserve(request.idempotency_key)
        if state == "done":
            return self._d.ledger.result(request.idempotency_key) or {"status": "unknown"}
        if state == "unknown":
            # Reserved earlier and never completed: the effect may or may not have happened.
            return {"status": "unknown", "reasons": ["dispatch_outcome_unknown"]}
        grant_id = decision.get("grant_id")
        grant = self._d.grants.get(grant_id) if grant_id else None
        if grant is None or not self._d.grants.consume(grant.grant_id, request):
            return self._finish(request, {"status": "denied", "reasons": ["grant_invalid"]})
        permit = AuthorizationDecision(
            decision_id=decision["decision_id"], action_id=request.action_id, decision="permit",
            policy_version="stf-v1", environment_id=request.environment_id, capability_grant_reference=grant.grant_id,
        )
        envelope = build_envelope(request, permit, grant, key=self._d.signing_key, nonce=request.idempotency_key)
        requested = {
            "mission_version": request.mission_version, "target": request.target_id,
            "environment": request.environment_id, "capability": request.capability,
            "action_class": request.action_class, "parameters_hash": parameters_hash(request.parameters),
            "tool_id": request.capability, "args_json": "{}",
        }
        try:
            answer = await self._d.gateway.execute(envelope, requested)
        except GatewayUnavailable:
            # Nothing was sent, so nothing can have happened.
            return self._finish(request, {"status": "denied", "reasons": ["gateway_unavailable"]})
        except GatewayOutcomeUnknown:
            # Sent, no answer: the effect may exist. Recorded as unknown so it is not repeated.
            return self._finish(request, {"status": "unknown", "reasons": ["gateway_response_lost"]})
        return self._finish(request, receipt_from(answer))

    def _finish(self, request: ActionRequest, result: dict[str, Any]) -> dict[str, Any]:
        self._d.ledger.complete(request.idempotency_key, result)
        emit("action.dispatched", mission_id=request.mission_id, action_id=request.action_id,
             environment_id=request.environment_id, status=result["status"])
        return result

    def all(self) -> list[Callable[..., Any]]:
        return [self.authorize_action, self.dispatch_action, self.verify_mission, self.revoke_grants, self.record_state,
                self.check_approval]
