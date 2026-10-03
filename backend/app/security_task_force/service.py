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
from app.security_task_force.evidence import EvidenceRecord
from app.security_task_force.qualification import TRUSTED_CAMPAIGNS, TRUSTED_SCENARIO_FAMILIES
from app.security_task_force.repository import StfRepository
from app.security_task_force.runtime_contracts import ApprovalRecord, RunView

# Governed Cyber Range control capabilities. The client's declared risk class is never trusted.
CAPABILITY_RISKS = {
    "range.health.verify": RiskClass.R1,
    "range.scenario.verify": RiskClass.R1,
    "range.scenario.start": RiskClass.R2,
    "range.campaign.verify": RiskClass.R1,
    "range.campaign.start": RiskClass.R2,
    "range.campaign.advance": RiskClass.R2,
    "range.reset": RiskClass.R2,
}
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

    async def record_evidence(
        self,
        creator: Actor,
        mission_id: str,
        run_id: str,
        execution_id: str,
        *,
        scenario_id: str,
        kind: str,
        source: str,
        payload: dict,
        acquired_at: str | None = None,
    ) -> EvidenceRecord:
        if kind not in {"attack", "defense"}:
            raise ValueError("kind must be attack or defense")
        if scenario_id not in TRUSTED_SCENARIO_FAMILIES:
            raise ValueError("scenario is not a trusted qualification scenario")
        if not source.strip() or len(source) > 128:
            raise ValueError("source is required and must be at most 128 characters")
        run = await self._owned(creator, run_id, mission_id=mission_id)
        if run.state not in {"RUNNING", "VERIFYING", "COMPLETED"}:
            raise RunConflict("the run is not accepting training evidence")
        if await self.repository.get_qualification(run_id) is not None:
            raise RunConflict("qualification is already finalized")
        dispatch = await self.repository.get_dispatch(execution_id, run_id)
        if dispatch is None or dispatch.status != "executed":
            raise LookupError("Executed dispatch not found")
        action = next(
            (item for item in run.plan_json if isinstance(item, dict) and item.get("action_id") == dispatch.action_id),
            None,
        )
        if action is None:
            raise LookupError("Dispatch action not found")
        scenario_start = next(
            (
                item for item in run.plan_json
                if isinstance(item, dict)
                and item.get("capability") == "range.scenario.start"
                and item.get("target_id") == scenario_id
            ),
            None,
        )
        campaign_start = next(
            (
                item for item in run.plan_json
                if isinstance(item, dict)
                and item.get("capability") == "range.campaign.start"
                and scenario_id in TRUSTED_CAMPAIGNS.get(str(item.get("target_id", "")), ())
            ),
            None,
        )
        authority_action = scenario_start or campaign_start
        if authority_action is None:
            raise ValueError("scenario was not part of this run")
        start_dispatch = await self.repository.get_dispatch_for_action(
            run_id, str(authority_action.get("action_id", ""))
        )
        if start_dispatch is None or start_dispatch.status != "executed":
            raise ValueError("scenario or campaign start is not proven by execution evidence")
        if scenario_start is None and campaign_start is not None:
            campaign_id = str(campaign_start.get("target_id", ""))
            members = TRUSTED_CAMPAIGNS[campaign_id]
            required_advances = members.index(scenario_id)
            advances = [
                item for item in run.plan_json
                if isinstance(item, dict)
                and item.get("capability") == "range.campaign.advance"
                and item.get("target_id") == campaign_id
            ]
            if len(advances) < required_advances:
                raise ValueError("campaign has not reached scenario")
            for advance in advances[:required_advances]:
                advance_dispatch = await self.repository.get_dispatch_for_action(
                    run_id, str(advance.get("action_id", ""))
                )
                if advance_dispatch is None or advance_dispatch.status != "executed":
                    raise ValueError("campaign has not reached scenario")
        record = EvidenceRecord.build(
            evidence_id=f"evidence:{uuid.uuid4()}",
            run_id=run_id,
            execution_id=execution_id,
            mission_id=mission_id,
            action_id=dispatch.action_id,
            task_id=str(action.get("task_id", "")),
            environment_id=str(action.get("environment_id", "")),
            source=source.strip(),
            kind=kind,
            acquired_at=acquired_at or datetime.now(timezone.utc).isoformat(),
            payload={**payload, "_scenario_id": scenario_id},
        )
        await self.repository.record_evidence(run_id, execution_id, record)
        await self.repository.project_verified_findings(run_id)
        return record

    async def findings(self, creator: Actor, mission_id: str, run_id: str) -> list[dict]:
        await self._owned(creator, run_id, mission_id=mission_id)
        return await self.repository.verified_findings(run_id)

    async def qualification(self, creator: Actor, mission_id: str, run_id: str) -> dict | None:
        await self._owned(creator, run_id, mission_id=mission_id)
        return await self.repository.get_qualification(run_id)

    async def finalize_qualification(self, creator: Actor, mission_id: str, run_id: str) -> dict:
        run = await self._owned(creator, run_id, mission_id=mission_id, lock=True)
        if run.state != "COMPLETED":
            raise RunConflict("qualification requires a completed run")
        existing = await self.repository.get_qualification(run_id)
        if existing is not None:
            return existing
        await self.repository.project_verified_findings(run_id)
        result = await self.repository.qualify_run(run_id)
        await self.repository.audit(
            "stf_qualification_finalized",
            run_id,
            {"run_id": run_id, "level": result.get("level"), "eligible": result.get("eligible")},
            actor_id=creator.id,
            actor_role=creator.role,
        )
        return result

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
            capability_risk = CAPABILITY_RISKS.get(action.capability)
            if capability_risk is None:
                raise ValueError("capability is not available to the Cyber Range integration")
            if action.environment_id not in contract.authorized_environments:
                raise RunForbidden("environment is not authorized by the contract")
            if action.target_id not in contract.authorized_targets or action.target_id in contract.excluded_targets:
                raise ValueError("target is not authorized by the contract")
            if action.action_class not in contract.allowed_action_classes:
                raise ValueError("action class is not allowed by the contract")
            if action.capability == "range.reset" and action.target_id != "range":
                raise ValueError("range.reset requires target_id=range")
            if capability_risk.rank > contract.risk_ceiling.rank:
                raise ValueError("the capability exceeds the contract risk ceiling")
            plan.append({**action.model_dump(mode="json"), "risk_class": capability_risk.value})
        return plan
