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
    StfContract,
    StfDispatch,
    StfGrant,
    StfInbox,
    StfOutbox,
    StfRun,
)
from app.repositories.domain import DomainRepository
from app.security_task_force.canonicalize import canonical_hash
from app.security_task_force.contracts import ActionRequest, CapabilityGrant
from app.security_task_force.mission_compiler import CompilationResult
from app.security_task_force.runtime_contracts import DispatchReceipt, OutboxLease, RunRecord

ACTOR = "stf-repository"
ACTOR_ROLE = "system"
LEASE_SECONDS = 60
TERMINAL_RUN_STATES = ("COMPLETED", "ABORTED")


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
        request_key: str, request_hash: str, plan_hash: str,
    ) -> RunRecord:
        inserted = await self.session.scalar(
            insert(StfRun).values(
                id=run_id, creator_id=creator_id, mission_id=mission_id, mission_version=mission_version,
                request_key=request_key, request_hash=request_hash, plan_hash=plan_hash,
                workflow_id=f"stf-{run_id}",
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

    async def issue_grant(self, run_id: str, grant: CapabilityGrant) -> None:
        self.session.add(StfGrant(
            grant_id=grant.grant_id, run_id=run_id, mission_id=grant.mission_id,
            mission_version=grant.mission_version, actor=grant.actor, capability=grant.capability,
            target_id=grant.target_id, environment_id=grant.environment_id, action_class=grant.action_class,
            expires_at=grant.expires_at, max_invocations=grant.max_invocations,
        ))
        await self.session.flush()

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
        await self._domain.add_event(event_type, "stf_run", run_id, ACTOR, ACTOR_ROLE, run_id, payload)
