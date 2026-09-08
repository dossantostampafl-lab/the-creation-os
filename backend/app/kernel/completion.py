from __future__ import annotations

from app.core.domain import MissionStatus


class CompletionError(ValueError):
    pass


def completion_target(task_statuses: list[str]) -> MissionStatus | None:
    if not task_statuses:
        raise CompletionError("Mission has no Tasks")
    if any(status in {"FAILED", "BLOCKED"} for status in task_statuses):
        return MissionStatus.FAILED
    if all(status == "SUCCEEDED" for status in task_statuses):
        return MissionStatus.MANIFESTED
    if any(status == "RUNNING" for status in task_statuses):
        return MissionStatus.EXECUTING
    return None
