from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity

from .authorization import authorize_and_grant, authorize_decision
from .contract_store import ContractStore
from .contracts import ActionRequest, AuthorizationDecision, MissionContract
from .envelope import build_envelope, parameters_hash
from .gateway_client import GatewayClient, GatewayOutcomeUnknown, GatewayUnavailable
from .grants import GrantStore, build_grant
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
    async def authorize_action(
        self, mission_id: str, action: dict[str, Any], approval: str | None, run_id: str | None = None
    ) -> dict[str, Any]:
        request = ActionRequest.model_validate(action)
        if not self._d.kill_switch.dispatch_allowed(mission_id):
            return {"decision": "deny", "reasons": ["kill_switch"]}
        if run_id is not None and self._d.session_factory is not None:
            decision = await self._authorize_persisted(mission_id, request, approval, run_id)
        else:
            contract = self._d.contracts.get(mission_id)
            if contract is None:
                return {"decision": "deny", "reasons": ["mission_unknown"]}
            decision = await authorize_and_grant(
                contract, request, grants=self._d.grants, policy=self._d.policy,
                creator_approval_reference=approval,
            )
        emit("action.decided", mission_id=mission_id, action_id=request.action_id,
             environment_id=request.environment_id, decision=decision.decision, reasons=decision.reason_codes)
        return {"decision": decision.decision, "reasons": decision.reason_codes,
                "decision_id": decision.decision_id, "grant_id": decision.capability_grant_reference,
                "expires_at": decision.expires_at.isoformat() if decision.expires_at else None}

    async def _authorize_persisted(
        self, mission_id: str, request: ActionRequest, approval: str | None, run_id: str
    ) -> AuthorizationDecision:
        if self._d.session_factory is None:
            return AuthorizationDecision(
                decision_id=f"decision:{request.action_id}", action_id=request.action_id, decision="deny",
                policy_version="stf-v1", environment_id=request.environment_id,
                reason_codes=["database_authority_unavailable"],
            )
        from .repository import StfRepository

        async with self._d.session_factory() as session:
            repository = StfRepository(session)
            run = await repository.get_run(run_id, lock=True)
            if (
                run is None
                or run.mission_id != mission_id
                or run.mission_version != request.mission_version
                or run.desired_state != "RUN"
            ):
                return AuthorizationDecision(
                    decision_id=f"decision:{request.action_id}", action_id=request.action_id, decision="deny",
                    policy_version="stf-v1", environment_id=request.environment_id,
                    reason_codes=["run_not_authorizable"],
                )
            record = await repository.get_contract(run.creator_id, mission_id, run.mission_version)
            if record is None:
                return AuthorizationDecision(
                    decision_id=f"decision:{request.action_id}", action_id=request.action_id, decision="deny",
                    policy_version="stf-v1", environment_id=request.environment_id,
                    reason_codes=["mission_unknown"],
                )
            contract = MissionContract.model_validate(record.contract_json)
            decision = await authorize_decision(
                contract, request, policy=self._d.policy, creator_approval_reference=approval
            )
            if decision.decision != "permit":
                return decision
            grant = build_grant(request, not_after=contract.time_window.get("end") if contract.time_window else None)
            if not await repository.issue_grant(run_id, grant):
                return decision.model_copy(update={
                    "decision": "deny", "reason_codes": ["run_not_authorizable"],
                    "capability_grant_reference": None, "expires_at": None,
                })
            await session.commit()
            return decision.model_copy(update={
                "capability_grant_reference": grant.grant_id,
                "expires_at": grant.expires_at,
            })

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
    async def dispatch_action(
        self, action: dict[str, Any], decision: dict[str, Any], run_id: str | None = None
    ) -> dict[str, Any]:
        """Hand a permitted action to the gateway. Persisted runs reserve authority in PostgreSQL first."""
        request = ActionRequest.model_validate(action)
        if not self._d.kill_switch.dispatch_allowed(request.mission_id):
            return {"status": "denied", "reasons": ["kill_switch"]}
        if run_id is not None:
            return await self._dispatch_persisted(request, decision, run_id)

        state = self._d.ledger.reserve(request.idempotency_key)
        if state == "done":
            return self._d.ledger.result(request.idempotency_key) or {"status": "unknown"}
        if state == "unknown":
            return {"status": "unknown", "reasons": ["dispatch_outcome_unknown"]}
        grant_id = decision.get("grant_id")
        grant = self._d.grants.get(grant_id) if grant_id else None
        if grant is None or not self._d.grants.consume(grant.grant_id, request):
            return self._finish(request, {"status": "denied", "reasons": ["grant_invalid"]})
        return await self._execute_gateway(request, decision, grant, self._finish)

    async def _dispatch_persisted(
        self, request: ActionRequest, decision: dict[str, Any], run_id: str
    ) -> dict[str, Any]:
        if self._d.session_factory is None:
            return {"status": "denied", "reasons": ["database_authority_unavailable"]}
        from .repository import StfRepository

        grant_id = decision.get("grant_id")
        if not grant_id:
            return {"status": "denied", "reasons": ["grant_missing"]}

        async with self._d.session_factory() as session:
            repository = StfRepository(session)
            receipt = await repository.reserve_dispatch(run_id, request, grant_id)
            await session.commit()

        if receipt.status != "authorized":
            result = {"status": receipt.status, "reasons": list(receipt.reason_codes)}
            if receipt.status == "executed" and receipt.execution_id:
                result["execution_id"] = receipt.execution_id
            emit("action.dispatched", mission_id=request.mission_id, action_id=request.action_id,
                 environment_id=request.environment_id, status=result["status"])
            return result

        async with self._d.session_factory() as session:
            grant = await StfRepository(session).get_grant(grant_id, run_id)
        if grant is None:
            result = {"status": "denied", "reasons": ["grant_metadata_unavailable"]}
        else:
            result = await self._execute_gateway(request, decision, grant, None)

        assert receipt.execution_id is not None
        async with self._d.session_factory() as session:
            await StfRepository(session).record_outcome(
                receipt.execution_id, result["status"], result.get("reasons", [])
            )
            await session.commit()
        emit("action.dispatched", mission_id=request.mission_id, action_id=request.action_id,
             environment_id=request.environment_id, status=result["status"])
        return result

    async def _execute_gateway(
        self,
        request: ActionRequest,
        decision: dict[str, Any],
        grant: Any,
        finish: Callable[[ActionRequest, dict[str, Any]], dict[str, Any]] | None,
    ) -> dict[str, Any]:
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
            result = receipt_from(answer)
        except GatewayUnavailable:
            result = {"status": "denied", "reasons": ["gateway_unavailable"]}
        except GatewayOutcomeUnknown:
            result = {"status": "unknown", "reasons": ["gateway_response_lost"]}
        return finish(request, result) if finish is not None else result

    def _finish(self, request: ActionRequest, result: dict[str, Any]) -> dict[str, Any]:
        self._d.ledger.complete(request.idempotency_key, result)
        emit("action.dispatched", mission_id=request.mission_id, action_id=request.action_id,
             environment_id=request.environment_id, status=result["status"])
        return result

    def all(self) -> list[Callable[..., Any]]:
        return [self.authorize_action, self.dispatch_action, self.verify_mission, self.revoke_grants, self.record_state,
                self.check_approval]
