from __future__ import annotations

import pytest

from app.core.domain import MissionStatus
from app.kernel.completion import CompletionError, completion_target


def test_all_tasks_succeeded_manifests_mission() -> None:
    assert completion_target(["SUCCEEDED", "SUCCEEDED"]) is MissionStatus.MANIFESTED


def test_failed_or_blocked_task_fails_mission() -> None:
    assert completion_target(["SUCCEEDED", "FAILED"]) is MissionStatus.FAILED
    assert completion_target(["BLOCKED"]) is MissionStatus.FAILED


def test_running_task_keeps_mission_executing() -> None:
    assert completion_target(["SUCCEEDED", "RUNNING"]) is MissionStatus.EXECUTING


def test_pending_work_has_no_terminal_transition() -> None:
    assert completion_target(["SUCCEEDED", "PENDING"]) is None


def test_completion_requires_tasks() -> None:
    with pytest.raises(CompletionError):
        completion_target([])
