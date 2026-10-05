"""Delivers the outbox to Temporal: at most one workflow per run, signals that survive restarts.

A lease that is neither acknowledged nor marked dead simply expires and comes back, so a crash at any point
repeats delivery instead of losing it. Starting is safe to repeat because the workflow id is fixed and a
duplicate is rejected; after any uncertain answer the existing workflow's identity is checked before the
item is acknowledged. Signals are idempotent commands and are the only thing retried blindly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.observability.telemetry import traced
from app.security_task_force.repository import StfRepository
from app.security_task_force.runtime_contracts import OutboxLease
from app.security_task_force.telemetry import emit
from app.security_task_force.workflows import MissionWorkflow

TASK_QUEUE = "security-task-force"
APPROVAL_TIMEOUT_SECONDS = 3600


def _subject(lease: OutboxLease) -> str:
    return str(lease.payload.get("mission_id") or lease.payload.get("run_id") or "")


class TemporalDispatcher:
    def __init__(self, session_factory: Callable[[], AsyncSession], client: Client, *, batch: int = 20,
                 max_attempts: int = 10, task_queue: str = TASK_QUEUE) -> None:
        self._factory, self._client = session_factory, client
        self._batch, self._max_attempts, self._queue = batch, max_attempts, task_queue

    @traced("workers.stf.dispatch")
    async def dispatch_once(self) -> int:
        """Deliver what is due (starts before signals). Returns how many items were acknowledged."""
        acknowledged = 0
        for destination in ("start", "signal"):
            async with self._factory() as session:
                leases = await StfRepository(session).claim_outbox(destination, self._batch)
                await session.commit()
            for lease in leases:
                outcome = await self._deliver(lease)
                if outcome == "retry" and lease.attempts >= self._max_attempts:
                    outcome = "dead"
                if outcome == "retry":
                    continue  # the lease expires and the item comes back
                async with self._factory() as session:
                    repository = StfRepository(session)
                    done = await (repository.ack_outbox if outcome == "ack" else repository.mark_outbox_dead)(lease.id, lease.token)
                    await session.commit()
                acknowledged += int(outcome == "ack" and done)
                emit("outbox.delivered", mission_id=_subject(lease), destination=lease.destination, outbox_id=lease.id, outcome=outcome)
        return acknowledged

    async def _deliver(self, lease: OutboxLease) -> str:
        try:
            if lease.destination == "start":
                return await self._start(lease.payload)
            return await self._signal(lease.payload)
        except Exception as error:  # noqa: BLE001 - any uncertain failure means "try again", never "done"
            emit("outbox.delivery_failed", mission_id=_subject(lease), outbox_id=lease.id, error=type(error).__name__)
            return "retry"

    async def _start(self, payload: dict[str, Any]) -> str:
        workflow_id = payload["workflow_id"]
        plan = {"mission_id": payload["mission_id"], "run_id": payload["run_id"], "actions": payload["plan"],
                "approval_timeout_seconds": APPROVAL_TIMEOUT_SECONDS}
        try:
            await self._client.start_workflow(
                MissionWorkflow.run, plan, id=workflow_id, task_queue=self._queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE, id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                memo={"run_id": payload["run_id"], "plan_hash": payload["plan_hash"]},
            )
            return "ack"
        except WorkflowAlreadyStartedError:
            # An earlier attempt got through, or someone else owns this id: only the same run and plan is ours.
            description = await self._client.get_workflow_handle(workflow_id).describe()
            same = (await description.memo_value("run_id", default=None) == payload["run_id"]
                    and await description.memo_value("plan_hash", default=None) == payload["plan_hash"])
            return "ack" if same else "dead"

    async def _signal(self, payload: dict[str, Any]) -> str:
        handle = self._client.get_workflow_handle(payload["workflow_id"])
        if payload["signal"] == "approve":
            await handle.signal("approve", payload["approval_id"])
        else:
            await handle.signal("cancel", payload.get("reason") or "cancelled")
        return "ack"
