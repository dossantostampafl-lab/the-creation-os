"""Use cases for explicit Security Task Force runs.

Starting is a separate, authenticated act: compiling a Mission queues nothing. Everything here runs in the
caller's transaction (no commit) so a run, its Chronicle event and its outbox `start` command exist together
or not at all. A `202` is only ever sent after the caller commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import Actor, require_creator
from app.security_task_force.canonicalize import canonical_hash
from app.security_task_force.contracts import ActionRequest, MissionContract, RiskClass
from app.security_task_force.repository import StfRepository
from app.security_task_force.runtime_contracts import ApprovalRecord, RunView

# The only capability this integration can run, with its fixed classification. The client's declared
# risk class is never trusted to widen or narrow it.
CAPABILITY = "range.health.verify"
CAPABILITY_RISK = RiskClass.R1
APPROVAL_TTL = timedelta(minutes=10)
CLOSED_STATES = ("COMPLETED", "ABORTED", "CANCELLING")


class RunConflict(Exception):
    """The run is in a state that does not accept this command."""


class RunForbidden(PermissionError):
    """The plan asks for something the Creator's contract or this integration does not allow."""


class StfService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = StfRepository(session)

    # --- queries -----------------------------------------------------------------------------------

    async def active_run_ids(self, creator: Actor, mission_id: str) -> list[str]:
        require_creator(creator, "use the Security Task Force")
        return await self.repository.active_run_ids(creator.id, mission_id)

    async def get(self, creator: Actor, mission_id: str, run_id: str) -> RunView:
        run = await self._owned(creator, run_id, mission_id=mission_id)
        return self._view(run)

    # --- commands ----------------------------------------------------------------------------------

    async def start(self, creator: Actor, mission_id: str, actions: list[ActionRequest], request_key: str) -> RunView:
        require_creator(creator, "start a Security Task Force run")
        if not request_key.strip():
            raise ValueError("an idempotency key is required")
        record = await self.repository.get_contract(creator.id, mission_id)
        if record is None:
            raise LookupError("Mission not found")
        contract = MissionContract.model_validate(record.contract_json)
        plan = self._validated_plan(contract, actions)

        request_hash = canonical_hash({"mission_id": mission_id, "actions": [a.model_dump(mode="json") for a in actions]})
        plan_hash = canonical_hash(plan)
        run = await self.repository.create_run(
            creator_id=creator.id, run_id=str(uuid.uuid4()), mission_id=mission_id,
            mission_version=contract.mission_version, request_key=request_key, request_hash=request_hash,
            plan_hash=plan_hash, plan=plan)
        if run.created:
            await self.repository.audit("stf_run_queued", run.run_id, {
                "run_id": run.run_id, "mission_id": mission_id, "mission_version": contract.mission_version,
                "plan_hash": plan_hash, "actions": len(plan)}, actor_id=creator.id, actor_role=creator.role)
            await self.repository.add_outbox("start", {
                "run_id": run.run_id, "workflow_id": run.workflow_id, "mission_id": mission_id,
                "mission_version": contract.mission_version, "plan_hash": plan_hash, "plan": plan})
        stored = await self.repository.get_run(run.run_id)
        assert stored is not None
        return self._view(stored)

    async def approve(self, creator: Actor, run_id: str, action_id: str, decision: str) -> ApprovalRecord:
        if decision not in {"approve", "deny"}:
            raise ValueError("decision must be approve or deny")
        run = await self._owned(creator, run_id, lock=True)
        if run.desired_state != "RUN" or run.state in CLOSED_STATES:
            raise RunConflict("the run no longer takes approvals")
        action = next((item for item in run.plan_json if item["action_id"] == action_id), None)
        if action is None:
            raise ValueError("the run has no such action")
        approval = await self.repository.add_approval(
            creator_id=creator.id, run_id=run_id, action_id=action_id, parameters_hash=canonical_hash(action["parameters"]),
            expires_at=datetime.now(timezone.utc) + APPROVAL_TTL, decision=decision)
        await self.repository.audit("stf_creator_decision", run_id, {
            "run_id": run_id, "action_id": action_id, "decision": decision, "approval_id": approval.id},
            actor_id=creator.id, actor_role=creator.role)
        await self.repository.add_outbox("signal", {"run_id": run_id, "workflow_id": run.workflow_id,
                                                    "signal": "approve", "approval_id": approval.id})
        return ApprovalRecord(approval.id, creator.id, run_id, action_id, approval.parameters_hash,
                              approval.expires_at, decision)

    async def cancel(self, creator: Actor, run_id: str, reason: str) -> RunView:
        run = await self._owned(creator, run_id)
        if run.state not in ("COMPLETED", "ABORTED"):
            # Intent and revocation are written first; the signal to the workflow follows from the outbox.
            await self.repository.revoke_run(run_id)
            await self.repository.audit("stf_run_cancel_requested", run_id, {"run_id": run_id, "reason": reason},
                                        actor_id=creator.id, actor_role=creator.role)
            await self.repository.add_outbox("signal", {"run_id": run_id, "workflow_id": run.workflow_id,
                                                        "signal": "cancel", "reason": reason})
        await self.session.refresh(run)
        return self._view(run)

    # --- internals ---------------------------------------------------------------------------------

    async def _owned(self, creator: Actor, run_id: str, *, mission_id: str | None = None, lock: bool = False):
        require_creator(creator, "use the Security Task Force")
        run = await self.repository.get_run(run_id, lock=lock)
        if run is None or run.creator_id != creator.id or (mission_id and run.mission_id != mission_id):
            raise LookupError("Run not found")
        return run

    @staticmethod
    def _view(run) -> RunView:
        return RunView(run.id, run.mission_id, run.mission_version, run.state, run.desired_state, run.plan_hash,
                       run.workflow_id)

    @staticmethod
    def _validated_plan(contract: MissionContract, actions: list[ActionRequest]) -> list[dict]:
        if not actions:
            raise ValueError("a run needs at least one action")
        if any(a.environment_id.startswith("real:") for a in actions):
            raise RunForbidden("real environments are not available to this integration")
        if len({a.action_id for a in actions}) != len(actions) or len({a.idempotency_key for a in actions}) != len(actions):
            raise ValueError("action ids and idempotency keys must be unique within a run")
        now = datetime.now(timezone.utc)
        window = contract.time_window
        if window and not window["start"] <= now <= window["end"]:
            raise ValueError("the mission is outside its time window")
        plan: list[dict] = []
        for action in actions:
            if action.mission_id != contract.mission_id or action.mission_version != contract.mission_version:
                raise ValueError("every action must belong to this mission and version")
            if action.capability != CAPABILITY:
                raise ValueError(f"only {CAPABILITY} can run")
            if action.environment_id not in contract.authorized_environments:
                raise RunForbidden("environment is not authorized by the contract")
            if action.target_id not in contract.authorized_targets or action.target_id in contract.excluded_targets:
                raise ValueError("target is not authorized by the contract")
            if action.action_class not in contract.allowed_action_classes:
                raise ValueError("action class is not allowed by the contract")
            if CAPABILITY_RISK.rank > contract.risk_ceiling.rank:
                raise ValueError("the capability exceeds the contract risk ceiling")
            plan.append({**action.model_dump(mode="json"), "risk_class": CAPABILITY_RISK.value})
        return plan
