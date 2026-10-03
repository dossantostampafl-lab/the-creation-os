"""Transactional authority for the Security Task Force.

Every method works inside the caller's transaction and never commits. Spending a grant, recording the
dispatch and writing the Chronicle event share one transaction: if the audit record cannot be written,
the authority is not spent. Concurrency is settled by row locks, never by application-side checks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_task_force import (
    StfApproval,
    StfContract,
    StfDispatch,
    StfEvidence,
    StfFinding,
    StfGrant,
    StfInbox,
    StfOutbox,
    StfQualification,
    StfRun,
)
from app.repositories.domain import DomainRepository
from app.security_task_force.canonicalize import canonical_hash
from app.security_task_force.contracts import ActionRequest, CapabilityGrant
from app.security_task_force.evidence import EvidenceRecord
from app.security_task_force.mission_compiler import CompilationResult
from app.security_task_force.qualification import (
    TRUSTED_PURPLE_SCENARIOS,
    TRUSTED_SCENARIO_FAMILIES,
    GateResult,
)
from app.security_task_force.qualification import (
    evaluate as evaluate_qualification,
)
from app.security_task_force.runtime_contracts import DispatchReceipt, OutboxLease, RunRecord
from app.security_task_force.verification import FindingStatus, verify_finding

ACTOR = "stf-repository"
ACTOR_ROLE = "system"
LEASE_SECONDS = 60
TERMINAL_RUN_STATES = ("COMPLETED", "ABORTED")
RUN_STATES = ("QUEUED", "RUNNING", "AWAITING_CREATOR", "VERIFYING", "CANCELLING", "UNKNOWN", "COMPLETED", "ABORTED")
_ALLOWED: dict[str, set[str]] = {
    "QUEUED": {"RUNNING", "CANCELLING", "ABORTED"},
    "RUNNING": {"AWAITING_CREATOR", "VERIFYING", "CANCELLING", "UNKNOWN", "ABORTED"},
    "AWAITING_CREATOR": {"RUNNING", "CANCELLING", "ABORTED"},
    "VERIFYING": {"COMPLETED", "CANCELLING", "UNKNOWN", "ABORTED"},
    "CANCELLING": {"UNKNOWN", "ABORTED"},
    "UNKNOWN": {"CANCELLING", "ABORTED"},
}


class IdempotencyConflict(Exception):
    """The same key was reused for different content."""


class ContractConflict(Exception):
    """A different contract was offered for an existing mission version. That is a new version."""


class StfRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._domain = DomainRepository(session)

    # --- contracts ---------------------------------------------------------------------------------

    async def save_contract(self, compiled: CompilationResult) -> None:
        record = compiled.record()
        contract = compiled.contract
        assert contract is not None
        await self.session.execute(
            insert(StfContract).values(
                id=str(uuid.uuid4()), creator_id=contract.creator_id, mission_id=contract.mission_id,
                mission_version=contract.mission_version, contract_hash=record["contract_hash"],
                contract_json=record["contract"], policy_version=record["policy_version"],
                compiler_version=record["compiler_version"],
            ).on_conflict_do_nothing(constraint="uq_stf_contract_version")
        )
        stored = await self.session.scalar(
            select(StfContract.contract_hash).where(
                StfContract.creator_id == contract.creator_id, StfContract.mission_id == contract.mission_id,
                StfContract.mission_version == contract.mission_version,
            )
        )
        if stored != record["contract_hash"]:
            raise ContractConflict(f"{contract.mission_id} v{contract.mission_version} already has another contract")

    # --- runs --------------------------------------------------------------------------------------

    async def create_run(
        self, *, creator_id: str, run_id: str, mission_id: str, mission_version: int,
        request_key: str, request_hash: str, plan_hash: str, plan: list[dict] | None = None,
    ) -> RunRecord:
        inserted = await self.session.scalar(
            insert(StfRun).values(
                id=run_id, creator_id=creator_id, mission_id=mission_id, mission_version=mission_version,
                request_key=request_key, request_hash=request_hash, plan_hash=plan_hash,
                plan_json=plan or [], workflow_id=f"stf:{run_id}",
            ).on_conflict_do_nothing(constraint="uq_stf_run_request").returning(StfRun.id)
        )
        run = await self.session.scalar(
            select(StfRun).where(StfRun.creator_id == creator_id, StfRun.mission_id == mission_id,
                                 StfRun.request_key == request_key)
        )
        assert run is not None
        if run.request_hash != request_hash:
            raise IdempotencyConflict(f"request key {request_key!r} was used for different content")
        return RunRecord(run.id, run.workflow_id, run.state, run.desired_state, created=inserted is not None)

    async def revoke_run(self, run_id: str) -> None:
        """Cancel is a durable desired state plus revoked grants; nothing after it can be authorized."""
        run = await self._lock_run(run_id)
        if run is None:
            return
        if run.state not in TERMINAL_RUN_STATES:
            run.desired_state = "CANCEL"
            run.state = "CANCELLING"
            run.updated_at = datetime.now(timezone.utc)
        await self.session.execute(update(StfGrant).where(StfGrant.run_id == run_id).values(revoked=True))
        await self._audit("stf.run.revoked", run_id, {"run_id": run_id})
        await self.session.flush()

    # --- grants and dispatch -----------------------------------------------------------------------

    async def issue_grant(self, run_id: str, grant: CapabilityGrant) -> bool:
        """Persist a grant only while the locked run still accepts authority."""
        run = await self._lock_run(run_id)
        if (
            run is None
            or run.desired_state != "RUN"
            or run.state != "RUNNING"
            or run.mission_id != grant.mission_id
            or run.mission_version != grant.mission_version
        ):
            return False
        self.session.add(StfGrant(
            grant_id=grant.grant_id, run_id=run_id, mission_id=grant.mission_id,
            mission_version=grant.mission_version, actor=grant.actor, capability=grant.capability,
            target_id=grant.target_id, environment_id=grant.environment_id, action_class=grant.action_class,
            expires_at=grant.expires_at, max_invocations=grant.max_invocations,
        ))
        await self.session.flush()
        return True

    async def reserve_dispatch(self, run_id: str, action: ActionRequest, grant_id: str) -> DispatchReceipt:
        request_hash = canonical_hash(action.model_dump(mode="json"))
        run = await self._lock_run(run_id)  # serializes with cancel and with every other dispatch of this run
        if run is None:
            return await self._deny(run_id, action, ["run_unknown"])

        existing = await self.session.scalar(
            select(StfDispatch).where(
                StfDispatch.run_id == run_id,
                (StfDispatch.idempotency_key == action.idempotency_key) | (StfDispatch.action_id == action.action_id),
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash or existing.idempotency_key != action.idempotency_key:
                raise IdempotencyConflict(f"{action.idempotency_key!r} was used for a different action")
            return DispatchReceipt(existing.status, existing.execution_id, list(existing.reason_codes))

        if run.desired_state == "CANCEL" or run.state in TERMINAL_RUN_STATES:
            return await self._deny(run_id, action, ["run_cancelled"])
        if run.state != "RUNNING":
            return await self._deny(run_id, action, ["run_not_dispatchable"])
        if run.mission_version != action.mission_version or run.mission_id != action.mission_id:
            return await self._deny(run_id, action, ["mission_version_mismatch"])

        grant = await self.session.scalar(
            select(StfGrant).where(StfGrant.grant_id == grant_id, StfGrant.run_id == run_id).with_for_update()
        )
        reasons = self._grant_refusal(grant, action)
        if reasons:
            return await self._deny(run_id, action, reasons)
        assert grant is not None

        grant.invocations += 1
        dispatch = StfDispatch(
            run_id=run_id, action_id=action.action_id, idempotency_key=action.idempotency_key,
            request_hash=request_hash, grant_id=grant_id, status="authorized", reason_codes=[],
        )
        self.session.add(dispatch)
        await self.session.flush()
        await self._audit("stf.dispatch.authorized", run_id, {
            "run_id": run_id, "action_id": action.action_id, "execution_id": dispatch.execution_id,
            "grant_id": grant_id, "capability": action.capability, "environment_id": action.environment_id,
        })
        return DispatchReceipt("authorized", dispatch.execution_id, [])

    async def record_outcome(self, execution_id: str, status: str, reason_codes: list[str] | None = None,
                             evidence_id: str | None = None) -> None:
        values: dict = {"status": status, "reason_codes": reason_codes or [], "updated_at": datetime.now(timezone.utc)}
        if evidence_id is not None:
            values["evidence_id"] = evidence_id
        await self.session.execute(update(StfDispatch).where(StfDispatch.execution_id == execution_id).values(**values))


    async def record_evidence(self, run_id: str, execution_id: str, evidence: EvidenceRecord) -> None:
        """Persist redacted immutable evidence only when every correlation key matches the reserved dispatch."""
        if not evidence.integrity_ok():
            raise ValueError("evidence integrity check failed")
        run = await self.get_run(run_id)
        dispatch = await self.session.scalar(
            select(StfDispatch).where(
                StfDispatch.run_id == run_id,
                StfDispatch.execution_id == execution_id,
            )
        )
        if run is None or dispatch is None:
            raise ValueError("evidence correlation target not found")
        if evidence.kind in {"attack", "defense"} and dispatch.status != "executed":
            raise ValueError("attack or defense evidence requires an executed dispatch")
        action = next(
            (item for item in run.plan_json if isinstance(item, dict) and item.get("action_id") == dispatch.action_id),
            None,
        )
        if action is None:
            raise ValueError("evidence correlation action not found")
        if (
            evidence.run_id != run_id
            or evidence.execution_id != execution_id
            or evidence.mission_id != run.mission_id
            or evidence.action_id != dispatch.action_id
            or evidence.task_id != action.get("task_id")
            or evidence.environment_id != action.get("environment_id")
        ):
            raise ValueError("evidence correlation mismatch")

        existing = await self.session.get(StfEvidence, evidence.evidence_id)
        if existing is not None:
            if existing.sha256 != evidence.sha256:
                raise IdempotencyConflict(f"evidence id {evidence.evidence_id!r} has different content")
            return

        self.session.add(StfEvidence(
            evidence_id=evidence.evidence_id,
            run_id=run_id,
            execution_id=execution_id,
            mission_id=evidence.mission_id,
            action_id=evidence.action_id,
            task_id=evidence.task_id,
            environment_id=evidence.environment_id,
            source=evidence.source,
            kind=evidence.kind,
            acquired_at=evidence.acquired_at,
            payload=evidence.payload,
            sha256=evidence.sha256,
        ))
        await self.session.flush()
        await self._audit("stf.evidence.recorded", run_id, evidence.chronicle_payload())

    async def verify_run_evidence(self, run_id: str) -> bool:
        """A persisted run verifies only when every planned action has intact, correlated execution evidence."""
        run = await self.get_run(run_id)
        if run is None or not run.plan_json:
            return False
        dispatches = (await self.session.scalars(
            select(StfDispatch).where(StfDispatch.run_id == run_id, StfDispatch.status == "executed")
        )).all()
        by_action = {item.action_id: item for item in dispatches}
        for action in run.plan_json:
            if not isinstance(action, dict):
                return False
            dispatch = by_action.get(str(action.get("action_id", "")))
            if dispatch is None or not dispatch.evidence_id:
                return False
            row = await self.session.get(StfEvidence, dispatch.evidence_id)
            if row is None:
                return False
            record = EvidenceRecord(
                evidence_id=row.evidence_id,
                mission_id=row.mission_id,
                action_id=row.action_id,
                task_id=row.task_id,
                environment_id=row.environment_id,
                source=row.source,
                kind=row.kind,
                acquired_at=row.acquired_at,
                payload=dict(row.payload),
                sha256=row.sha256,
                run_id=row.run_id,
                execution_id=row.execution_id,
            )
            if (
                not record.integrity_ok()
                or record.run_id != run_id
                or record.execution_id != dispatch.execution_id
                or record.mission_id != run.mission_id
                or record.action_id != action.get("action_id")
                or record.task_id != action.get("task_id")
                or record.environment_id != action.get("environment_id")
            ):
                return False
        return True


    @staticmethod
    def _evidence_record(row: StfEvidence) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=row.evidence_id,
            mission_id=row.mission_id,
            action_id=row.action_id,
            task_id=row.task_id,
            environment_id=row.environment_id,
            source=row.source,
            kind=row.kind,
            acquired_at=row.acquired_at,
            payload=dict(row.payload),
            sha256=row.sha256,
            run_id=row.run_id,
            execution_id=row.execution_id,
        )

    async def evidence_records(
        self, run_id: str, *, action_id: str | None = None, kind: str | None = None
    ) -> list[EvidenceRecord]:
        stmt = select(StfEvidence).where(StfEvidence.run_id == run_id)
        if action_id is not None:
            stmt = stmt.where(StfEvidence.action_id == action_id)
        if kind is not None:
            stmt = stmt.where(StfEvidence.kind == kind)
        rows = (await self.session.scalars(stmt.order_by(StfEvidence.created_at, StfEvidence.evidence_id))).all()
        return [self._evidence_record(row) for row in rows]

    async def project_verified_findings(self, run_id: str) -> list[dict]:
        """Project only confirmed findings; Chronicle receives references and hashes, never evidence bodies."""
        run = await self.get_run(run_id)
        if run is None:
            return []
        dispatches = (await self.session.scalars(
            select(StfDispatch).where(StfDispatch.run_id == run_id)
        )).all()
        by_action = {row.action_id: row for row in dispatches}
        records = await self.evidence_records(run_id)
        grouped: dict[str, dict[str, list[EvidenceRecord]]] = {}
        for record in records:
            grouped.setdefault(record.action_id, {}).setdefault(record.kind, []).append(record)

        for action in run.plan_json:
            if not isinstance(action, dict):
                continue
            action_id = str(action.get("action_id", ""))
            attack_records = grouped.get(action_id, {}).get("attack", [])
            if not attack_records:
                continue
            defense_records = grouped.get(action_id, {}).get("defense", [])
            params = action.get("parameters")
            if not isinstance(params, dict):
                params = {}
            replay_refs: list[str] = []
            for replay in run.plan_json:
                if not isinstance(replay, dict):
                    continue
                replay_params = replay.get("parameters")
                if not isinstance(replay_params, dict):
                    replay_params = {}
                if replay_params.get("replay_of") != action_id:
                    continue
                replay_dispatch = by_action.get(str(replay.get("action_id", "")))
                if replay_dispatch is not None and replay_dispatch.status == "executed" and replay_dispatch.evidence_id:
                    replay_refs.append(replay_dispatch.evidence_id)

            attack = attack_records[-1]
            defense = defense_records[-1] if defense_records else None
            scenario_id = str(attack.payload.get("_scenario_id", ""))
            if scenario_id not in TRUSTED_SCENARIO_FAMILIES:
                continue
            if defense is not None and str(defense.payload.get("_scenario_id", "")) != scenario_id:
                continue
            verdict = verify_finding(
                attack,
                defense,
                purple_required=scenario_id in TRUSTED_PURPLE_SCENARIOS,
                reproduced=bool(replay_refs),
                mission_id=run.mission_id,
                action_id=action_id,
                environment_id=str(action.get("environment_id", "")),
            )
            if verdict.status != FindingStatus.CONFIRMED.value:
                continue

            finding_id = "finding:" + canonical_hash({
                "run_id": run_id,
                "action_id": action_id,
                "attack": attack.evidence_id,
                "defense": defense.evidence_id if defense else None,
                "replay": replay_refs,
            })[:48]
            title = str(params.get("finding_title") or f"Verified finding for {action_id}")[:256]
            inserted = await self.session.scalar(
                insert(StfFinding).values(
                    finding_id=finding_id,
                    run_id=run_id,
                    mission_id=run.mission_id,
                    action_id=action_id,
                    task_id=str(action.get("task_id", "")),
                    environment_id=str(action.get("environment_id", "")),
                    title=title,
                    status=FindingStatus.CONFIRMED.value,
                    reason=verdict.reason,
                    attack_evidence=[attack.evidence_id],
                    defense_evidence=[defense.evidence_id] if defense else [],
                    reproduced=True,
                ).on_conflict_do_nothing(index_elements=[StfFinding.finding_id]).returning(StfFinding.finding_id)
            )
            if inserted is not None:
                await self._audit("stf.finding.confirmed", run_id, {
                    "finding_id": finding_id,
                    "run_id": run_id,
                    "mission_id": run.mission_id,
                    "action_id": action_id,
                    "environment_id": str(action.get("environment_id", "")),
                    "attack_evidence": [attack.evidence_id],
                    "defense_evidence": [defense.evidence_id] if defense else [],
                    "replay_evidence": replay_refs,
                    "reason": verdict.reason,
                })
        return await self.verified_findings(run_id)

    async def verified_findings(self, run_id: str) -> list[dict]:
        rows = (await self.session.scalars(
            select(StfFinding).where(
                StfFinding.run_id == run_id,
                StfFinding.status == FindingStatus.CONFIRMED.value,
            ).order_by(StfFinding.created_at, StfFinding.finding_id)
        )).all()
        return [{
            "finding_id": row.finding_id,
            "run_id": row.run_id,
            "mission_id": row.mission_id,
            "action_id": row.action_id,
            "task_id": row.task_id,
            "environment_id": row.environment_id,
            "title": row.title,
            "status": row.status,
            "reason": row.reason,
            "attack_evidence": list(row.attack_evidence),
            "defense_evidence": list(row.defense_evidence),
            "reproduced": row.reproduced,
        } for row in rows]

    async def qualify_run(self, run_id: str) -> dict:
        """Derive the SH ladder input from persisted run/evidence state and store one immutable result."""
        existing = await self.session.get(StfQualification, run_id)
        if existing is not None:
            return self._qualification_dict(existing)

        run = await self.get_run(run_id)
        if run is None or not run.plan_json:
            return {
                "eligible": False, "level": None, "score": 0, "failed_gates": ["run_missing"],
                "passed_gates": [], "reasons": ["run_missing"], "evidence_refs": [],
            }

        dispatches = (await self.session.scalars(
            select(StfDispatch).where(StfDispatch.run_id == run_id)
        )).all()
        by_action = {row.action_id: row for row in dispatches}
        records = await self.evidence_records(run_id)
        evidence_by_id = {row.evidence_id: row for row in records}
        evidence_refs = sorted(evidence_by_id)
        plan_refs = (f"plan:{run.plan_hash}",)

        all_contained = all(
            isinstance(action, dict) and str(action.get("environment_id", "")).startswith("cyber_range:")
            for action in run.plan_json
        )
        evidence_integrity = bool(records) and all(record.integrity_ok() for record in records)
        all_executed = True
        executed_count = 0
        for action in run.plan_json:
            if not isinstance(action, dict):
                all_executed = False
                continue
            dispatch = by_action.get(str(action.get("action_id", "")))
            ok = bool(
                dispatch is not None
                and dispatch.status == "executed"
                and dispatch.evidence_id
                and dispatch.evidence_id in evidence_by_id
            )
            all_executed = all_executed and ok
            executed_count += int(ok)

        high_risk = [
            action for action in run.plan_json
            if isinstance(action, dict) and str(action.get("risk_class", "")) in {"R3", "R4"}
        ]
        approval_refs: list[str] = []
        approvals_ok = True
        if high_risk:
            approvals = (await self.session.scalars(
                select(StfApproval).where(
                    StfApproval.run_id == run_id,
                    StfApproval.decision == "approve",
                )
            )).all()
            approved_actions = {row.action_id for row in approvals}
            approvals_ok = all(str(action.get("action_id", "")) in approved_actions for action in high_risk)
            approval_refs = [f"approval:{row.id}" for row in approvals]
        else:
            approval_refs = list(plan_refs)

        replay_refs: list[str] = []
        for action in run.plan_json:
            if not isinstance(action, dict):
                continue
            dispatch = by_action.get(str(action.get("action_id", "")))
            params = action.get("parameters")
            if not isinstance(params, dict):
                params = {}
            if params.get("replay_of") and dispatch is not None and dispatch.status == "executed" and dispatch.evidence_id:
                replay_refs.append(dispatch.evidence_id)

        scenario_refs: dict[str, list[str]] = {name: [] for name in TRUSTED_SCENARIO_FAMILIES.values()}
        findings = (await self.session.scalars(
            select(StfFinding).where(
                StfFinding.run_id == run_id,
                StfFinding.status == FindingStatus.CONFIRMED.value,
            )
        )).all()
        for finding in findings:
            finding_refs = list(finding.attack_evidence) + list(finding.defense_evidence)
            finding_scenarios = {
                str(evidence_by_id[ref].payload.get("_scenario_id", ""))
                for ref in finding_refs
                if ref in evidence_by_id
            }
            for scenario_id in finding_scenarios:
                family = TRUSTED_SCENARIO_FAMILIES.get(scenario_id)
                if family is not None:
                    scenario_refs[family].extend(finding_refs)

        required_coverage = all(bool(scenario_refs[name]) for name in scenario_refs)
        refs = tuple(evidence_refs or plan_refs)
        gates = {
            "containment": GateResult(all_contained, refs),
            "evidence_integrity": GateResult(evidence_integrity, tuple(evidence_refs)),
            "policy_compliance": GateResult(all_executed, refs),
            "creator_approval_gates": GateResult(approvals_ok, tuple(approval_refs)),
            "reproducibility": GateResult(bool(replay_refs), tuple(replay_refs)),
            "full_required_coverage": GateResult(all_executed and required_coverage, tuple(evidence_refs)),
        }
        scenario_results = {
            family: GateResult(bool(items), tuple(sorted(set(items))))
            for family, items in scenario_refs.items()
        }
        score = int(round(100 * executed_count / len(run.plan_json))) if run.plan_json else 0
        result = evaluate_qualification(gates=gates, scenarios=scenario_results, score=score)
        all_refs = sorted(set(evidence_refs + approval_refs + list(plan_refs)))
        row = StfQualification(
            run_id=run_id,
            eligible=result.eligible,
            level=result.level,
            score=score,
            failed_gates=result.failed_gates,
            passed_gates=result.passed_gates,
            reasons=result.reasons,
            evidence_refs=all_refs,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit("stf.qualification.recorded", run_id, {
            "run_id": run_id,
            "eligible": result.eligible,
            "level": result.level,
            "score": score,
            "failed_gates": result.failed_gates,
            "passed_gates": result.passed_gates,
            "reasons": result.reasons,
            "evidence_refs": all_refs,
        })
        return self._qualification_dict(row)

    @staticmethod
    def _qualification_dict(row: StfQualification) -> dict:
        return {
            "run_id": row.run_id,
            "eligible": row.eligible,
            "level": row.level,
            "score": row.score,
            "failed_gates": list(row.failed_gates),
            "passed_gates": list(row.passed_gates),
            "reasons": list(row.reasons),
            "evidence_refs": list(row.evidence_refs),
        }

    # --- outbox and inbox --------------------------------------------------------------------------

    async def add_outbox(self, destination: str, payload: dict) -> str:
        item = StfOutbox(destination=destination, payload=payload)
        self.session.add(item)
        await self.session.flush()
        return item.id

    async def claim_outbox(self, destination: str, limit: int, lease_seconds: int = LEASE_SECONDS) -> list[OutboxLease]:
        now = datetime.now(timezone.utc)
        rows = (await self.session.scalars(
            select(StfOutbox).where(
                StfOutbox.destination == destination,
                (StfOutbox.status == "pending")
                | ((StfOutbox.status == "leased") & (StfOutbox.lease_expires_at < now)),
            ).order_by(StfOutbox.created_at).limit(limit).with_for_update(skip_locked=True)
        )).all()
        leases = []
        for row in rows:
            row.status, row.lease_token = "leased", str(uuid.uuid4())
            row.lease_expires_at, row.attempts, row.updated_at = now + timedelta(seconds=lease_seconds), row.attempts + 1, now
            leases.append(OutboxLease(row.id, row.destination, dict(row.payload), row.lease_token, row.attempts))
        await self.session.flush()
        return leases

    async def ack_outbox(self, outbox_id: str, token: str) -> bool:
        result = await self.session.execute(
            update(StfOutbox)
            .where(StfOutbox.id == outbox_id, StfOutbox.lease_token == token, StfOutbox.status == "leased")
            .values(status="acked", updated_at=datetime.now(timezone.utc))
        )
        return cast(CursorResult, result).rowcount == 1

    async def record_inbox(self, consumer: str, event_id: str) -> bool:
        """True the first time a consumer sees an event, False for every redelivery."""
        result = await self.session.scalar(
            insert(StfInbox).values(consumer=consumer, event_id=event_id).on_conflict_do_nothing().returning(StfInbox.event_id)
        )
        return result is not None

    # --- internals ---------------------------------------------------------------------------------

    async def _lock_run(self, run_id: str) -> StfRun | None:
        return await self.session.scalar(select(StfRun).where(StfRun.id == run_id).with_for_update())

    @staticmethod
    def _grant_refusal(grant: StfGrant | None, action: ActionRequest) -> list[str]:
        if grant is None:
            return ["grant_missing"]
        if grant.revoked:
            return ["grant_revoked"]
        if grant.expires_at <= datetime.now(timezone.utc):
            return ["grant_expired"]
        if grant.invocations >= grant.max_invocations:
            return ["grant_exhausted"]
        bound = CapabilityGrant(
            grant_id=grant.grant_id, mission_id=grant.mission_id, mission_version=grant.mission_version,
            actor=grant.actor, capability=grant.capability, target_id=grant.target_id,
            environment_id=grant.environment_id, action_class=grant.action_class, expires_at=grant.expires_at,
            max_invocations=grant.max_invocations,
        )
        return [] if bound.matches(action, invocations=grant.invocations) else ["grant_mismatch"]

    async def _deny(self, run_id: str, action: ActionRequest, reasons: list[str]) -> DispatchReceipt:
        await self._audit("stf.dispatch.denied", run_id, {
            "run_id": run_id, "action_id": action.action_id, "reason_codes": reasons,
        })
        return DispatchReceipt("denied", None, reasons)

    async def _audit(self, event_type: str, run_id: str, payload: dict) -> None:
        await self.audit(event_type, run_id, payload)

    async def audit(self, event_type: str, run_id: str, payload: dict, actor_id: str = ACTOR,
                    actor_role: str = ACTOR_ROLE) -> None:
        await self._domain.add_event(event_type, "stf_run", run_id, actor_id, actor_role, run_id, payload)

    async def set_run_state(self, run_id: str, state: str) -> bool:
        """Conditional transition. A terminal run never reopens, and a run marked for cancel only moves toward its end."""
        run = await self._lock_run(run_id)
        if run is None or run.state in TERMINAL_RUN_STATES or state == run.state:
            return False
        if state not in RUN_STATES or state not in _ALLOWED[run.state]:
            return False
        if run.desired_state == "CANCEL" and state not in ("CANCELLING", "UNKNOWN", "ABORTED"):
            return False
        run.state, run.updated_at = state, datetime.now(timezone.utc)
        await self._audit("stf_run_state", run_id, {"run_id": run_id, "state": state})
        return True

    async def approval_matches(self, approval_id: str, run_id: str, action: dict) -> bool:
        """A stored, unexpired approve decision for this run, this action and exactly these parameters."""
        approval = await self.session.get(StfApproval, approval_id)
        run = await self.get_run(run_id)
        return (
            approval is not None and run is not None and approval.run_id == run_id
            and approval.creator_id == run.creator_id and approval.decision == "approve"
            and approval.action_id == action.get("action_id")
            and approval.parameters_hash == canonical_hash(action.get("parameters", {}))
            and approval.expires_at > datetime.now(timezone.utc) and run.desired_state == "RUN"
        )

    async def mark_outbox_dead(self, outbox_id: str, token: str) -> bool:
        result = await self.session.execute(
            update(StfOutbox).where(StfOutbox.id == outbox_id, StfOutbox.lease_token == token, StfOutbox.status == "leased")
            .values(status="dead", updated_at=datetime.now(timezone.utc)))
        return cast(CursorResult, result).rowcount == 1

    # --- reads -------------------------------------------------------------------------------------

    async def get_contract(self, creator_id: str, mission_id: str, version: int | None = None) -> StfContract | None:
        stmt = select(StfContract).where(StfContract.creator_id == creator_id, StfContract.mission_id == mission_id)
        stmt = stmt.where(StfContract.mission_version == version) if version else stmt.order_by(StfContract.mission_version.desc())
        return await self.session.scalar(stmt.limit(1))

    async def get_run(self, run_id: str, *, lock: bool = False) -> StfRun | None:
        stmt = select(StfRun).where(StfRun.id == run_id)
        return await self.session.scalar(stmt.with_for_update() if lock else stmt)

    async def get_grant(self, grant_id: str, run_id: str | None = None) -> CapabilityGrant | None:
        stmt = select(StfGrant).where(StfGrant.grant_id == grant_id)
        if run_id is not None:
            stmt = stmt.where(StfGrant.run_id == run_id)
        grant = await self.session.scalar(stmt)
        if grant is None:
            return None
        return CapabilityGrant(
            grant_id=grant.grant_id, mission_id=grant.mission_id, mission_version=grant.mission_version,
            actor=grant.actor, capability=grant.capability, target_id=grant.target_id,
            environment_id=grant.environment_id, action_class=grant.action_class, expires_at=grant.expires_at,
            max_invocations=grant.max_invocations, revoked=grant.revoked,
        )

    async def get_dispatch(self, execution_id: str, run_id: str | None = None) -> StfDispatch | None:
        stmt = select(StfDispatch).where(StfDispatch.execution_id == execution_id)
        if run_id is not None:
            stmt = stmt.where(StfDispatch.run_id == run_id)
        return await self.session.scalar(stmt)

    async def get_dispatch_for_action(self, run_id: str, action_id: str) -> StfDispatch | None:
        return await self.session.scalar(
            select(StfDispatch).where(
                StfDispatch.run_id == run_id,
                StfDispatch.action_id == action_id,
            )
        )

    async def get_qualification(self, run_id: str) -> dict | None:
        row = await self.session.get(StfQualification, run_id)
        return self._qualification_dict(row) if row is not None else None

    async def active_run_ids(self, creator_id: str, mission_id: str) -> list[str]:
        rows = await self.session.scalars(select(StfRun.id).where(
            StfRun.creator_id == creator_id, StfRun.mission_id == mission_id, StfRun.state.notin_(TERMINAL_RUN_STATES)))
        return list(rows.all())

    async def add_approval(self, *, creator_id: str, run_id: str, action_id: str, parameters_hash: str,
                           expires_at: datetime, decision: str) -> StfApproval:
        approval = StfApproval(creator_id=creator_id, run_id=run_id, action_id=action_id,
                               parameters_hash=parameters_hash, expires_at=expires_at, decision=decision)
        self.session.add(approval)
        await self.session.flush()
        return approval
