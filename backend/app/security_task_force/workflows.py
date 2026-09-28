from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

_SHORT = timedelta(seconds=30)
_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))
_ONCE = RetryPolicy(maximum_attempts=1)  # a state-changing dispatch is never retried by the engine


@workflow.defn
class MissionWorkflow:
    """Durable Mission run. Deterministic: no network, database or model call happens in here.

    plan = {"mission_id": str, "actions": [ActionRequest dict], "approval_timeout_seconds": int}
    """

    def __init__(self) -> None:
        self._approval: str | None = None
        self._cancel: str | None = None
        self._state = "AUTHORIZED"
        self._run_id: str | None = None

    @workflow.signal
    def approve(self, creator_approval_reference: str) -> None:
        self._approval = creator_approval_reference

    @workflow.signal
    def cancel(self, reason: str) -> None:
        self._cancel = reason or "cancelled"

    @workflow.query
    def status(self) -> str:
        return self._state

    async def _set(self, mission_id: str, state: str) -> None:
        self._state = state
        await workflow.execute_activity(
            "stf_record_state", args=[mission_id, state, self._run_id], start_to_close_timeout=_SHORT, retry_policy=_RETRY
        )

    async def _abort(self, mission_id: str) -> str:
        # Intent is recorded, grants are revoked and dispatch stopped before the terminal state is written.
        if self._cancel is not None:
            await self._set(mission_id, "CANCELLING")
        await workflow.execute_activity(
            "stf_revoke_grants", args=[mission_id, self._run_id], start_to_close_timeout=_SHORT,
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        await self._set(mission_id, "ABORTED")
        return "ABORTED"

    async def _await_approval(self, action: dict[str, Any], timeout_seconds: int) -> str | None:
        """Wait for an approval that actually matches this run and action; anything else keeps waiting."""
        deadline = workflow.time() + timeout_seconds
        while self._cancel is None:
            remaining = deadline - workflow.time()
            if remaining <= 0:
                return None
            try:
                await workflow.wait_condition(lambda: self._approval is not None or self._cancel is not None,
                                              timeout=timedelta(seconds=remaining))
            except TimeoutError:
                return None
            candidate, self._approval = self._approval, None
            if candidate is None or self._cancel is not None:
                continue
            if self._run_id is None:
                return candidate  # a run without a stored record has nothing to check the reference against
            valid: bool = await workflow.execute_activity(
                "stf_check_approval", args=[self._run_id, candidate, action],
                start_to_close_timeout=_SHORT, retry_policy=_RETRY)
            if valid:
                return candidate
        return None

    @workflow.run
    async def run(self, plan: dict[str, Any]) -> str:
        mission_id: str = plan["mission_id"]
        self._run_id = plan.get("run_id")
        if not plan.get("actions"):
            return await self._abort(mission_id)  # an empty plan proves nothing and can never complete
        await self._set(mission_id, "RUNNING")
        for action in plan["actions"]:
            if self._cancel is not None:
                return await self._abort(mission_id)
            approval: str | None = None
            while True:
                decision: dict[str, Any] = await workflow.execute_activity(
                    "stf_authorize_action", args=[mission_id, action, approval],
                    start_to_close_timeout=_SHORT, retry_policy=_RETRY,
                )
                if decision["decision"] == "permit":
                    break
                if decision["decision"] == "escalate" and decision["reasons"] == ["creator_approval_required"] and approval is None:
                    await self._set(mission_id, "AWAITING_CREATOR")
                    approval = await self._await_approval(action, plan.get("approval_timeout_seconds", 3600))
                    if approval is None:
                        return await self._abort(mission_id)
                    await self._set(mission_id, "RUNNING")
                    continue
                return await self._abort(mission_id)  # deny, or an escalation this run cannot resolve
            result: dict[str, Any] = await workflow.execute_activity(
                "stf_dispatch_action", args=[action, decision],
                start_to_close_timeout=_SHORT, retry_policy=_ONCE,
            )
            if result["status"] != "executed":
                return await self._abort(mission_id)
        if self._cancel is not None:
            return await self._abort(mission_id)
        await self._set(mission_id, "VERIFYING")
        verified: bool = await workflow.execute_activity(
            "stf_verify_mission", mission_id, start_to_close_timeout=_SHORT, retry_policy=_RETRY
        )
        if not verified:
            return await self._abort(mission_id)
        await self._set(mission_id, "COMPLETED")
        return "COMPLETED"
