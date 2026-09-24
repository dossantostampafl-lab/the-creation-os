from __future__ import annotations

from temporalio import workflow


@workflow.defn
class MissionWorkflow:
    @workflow.run
    async def run(self, mission_id: str) -> str:
        # Privileged actions are never embedded in workflow payloads.
        # Activities reload current authorization and grant state by action id.
        return f"AUTHORIZED:{mission_id}"
