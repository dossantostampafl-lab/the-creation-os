from __future__ import annotations

try:
    from temporalio import workflow
except ImportError:  # pragma: no cover
    workflow = None


if workflow:
    @workflow.defn
    class MissionWorkflow:
        @workflow.run
        async def run(self, mission_id: str) -> str:
            # Privileged actions are deliberately not embedded in workflow payloads.
            # Activities must reload current authorization/grant state by action id.
            return f"AUTHORIZED:{mission_id}"
else:
    class MissionWorkflow:  # type: ignore[no-redef]
        pass
