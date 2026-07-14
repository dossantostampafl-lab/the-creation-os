from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace

import pytest

from app.core.consolidation import ConsolidationError, build_consolidation
from app.services.consolidation import ConsolidationService
from app.services.domain import NotFoundError


def source_set():
    mission_id = str(uuid.uuid4())
    task_a, task_b = str(uuid.uuid4()), str(uuid.uuid4())
    capability_id, agent_id = str(uuid.uuid4()), str(uuid.uuid4())
    dispatch_a, dispatch_b = str(uuid.uuid4()), str(uuid.uuid4())
    mission = SimpleNamespace(id=mission_id, status="authorized")
    tasks = [
        SimpleNamespace(
            id=task_b,
            mission_id=mission_id,
            state="ready",
            name="Second",
            required_capability_id=capability_id,
            agent_id=None,
        ),
        SimpleNamespace(
            id=task_a,
            mission_id=mission_id,
            state="ready",
            name="First",
            required_capability_id=capability_id,
            agent_id=None,
        ),
    ]
    dependencies = [SimpleNamespace(task_id=task_b, dependency_id=task_a)]
    dispatches = [
        SimpleNamespace(
            id=dispatch_b,
            task_id=task_b,
            mission_id=mission_id,
            agent_id=agent_id,
            capability_id=capability_id,
            state="acknowledged",
        ),
        SimpleNamespace(
            id=dispatch_a,
            task_id=task_a,
            mission_id=mission_id,
            agent_id=agent_id,
            capability_id=capability_id,
            state="acknowledged",
        ),
    ]
    executions = [
        SimpleNamespace(
            id=str(uuid.uuid4()),
            dispatch_item_id=item.id,
            mission_id=mission_id,
            task_id=item.task_id,
            agent_id=agent_id,
            capability_id=capability_id,
            state="succeeded",
            output_payload={"task": item.task_id, "nested": {"b": 2, "a": 1}},
            result_metrics={"duration": 1},
            result_warnings=[],
        )
        for item in dispatches
    ]
    return mission, tasks, dependencies, dispatches, executions


def issue_codes(exc: pytest.ExceptionInfo[ConsolidationError]) -> set[str]:
    return {item.code for item in exc.value.issues}


def test_complete_consolidation_is_topological_deterministic_and_order_independent():
    sources = source_set()
    first = build_consolidation(*sources)
    shuffled = (
        sources[0],
        list(reversed(sources[1])),
        list(reversed(sources[2])),
        list(reversed(sources[3])),
        list(reversed(sources[4])),
    )
    second = build_consolidation(*shuffled)
    assert first.status == "complete"
    assert first.completeness == {"complete": True, "expected_tasks": 2, "consolidated_tasks": 2, "pending_tasks": 0}
    assert first.payload == second.payload
    assert first.fingerprint == second.fingerprint
    assert first.payload["tasks"][1]["dependencies"] == [first.payload["tasks"][0]["task_id"]]


def test_consolidation_does_not_mutate_sources():
    sources = source_set()
    before = copy.deepcopy(sources)
    build_consolidation(*sources)
    for current_group, original_group in zip(sources, before, strict=True):
        if isinstance(current_group, list):
            assert [vars(item) for item in current_group] == [vars(item) for item in original_group]
        else:
            assert vars(current_group) == vars(original_group)


def test_mission_without_tasks_is_incomplete():
    mission = SimpleNamespace(id=str(uuid.uuid4()), status="authorized")
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(mission, [], [], [], [])
    assert "mission_without_tasks" in issue_codes(exc)


def test_pending_task_is_rejected():
    sources = source_set()
    sources[1][0].state = "waiting"
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert "task_not_ready" in issue_codes(exc)


@pytest.mark.parametrize("state", ["pending", "accepted", "running"])
def test_non_terminal_execution_is_rejected(state):
    sources = source_set()
    sources[4][0].state = state
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert {"execution_not_terminal", "missing_successful_execution"} <= issue_codes(exc)


def test_execution_without_result_is_rejected():
    sources = source_set()
    sources[4][0].output_payload = None
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert {"execution_without_result", "missing_successful_execution"} <= issue_codes(exc)


def test_task_without_execution_is_rejected():
    sources = source_set()
    sources[4].pop()
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert "missing_successful_execution" in issue_codes(exc)


def test_dispatch_with_incompatible_capability_is_rejected():
    sources = source_set()
    sources[3][0].capability_id = str(uuid.uuid4())
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert "dispatch_capability_mismatch" in issue_codes(exc)


@pytest.mark.parametrize(
    ("target", "field", "code"),
    [
        ("task", "mission_id", "task_mission_mismatch"),
        ("dispatch", "mission_id", "dispatch_mission_mismatch"),
        ("execution", "mission_id", "execution_mission_mismatch"),
        ("execution", "task_id", "execution_task_mismatch"),
        ("execution", "agent_id", "execution_agent_mismatch"),
        ("execution", "capability_id", "execution_capability_mismatch"),
    ],
)
def test_incompatible_relations_are_rejected(target, field, code):
    sources = source_set()
    groups = {"task": sources[1], "dispatch": sources[3], "execution": sources[4]}
    setattr(groups[target][0], field, str(uuid.uuid4()))
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert code in issue_codes(exc)


def test_orphan_reference_is_rejected():
    sources = source_set()
    sources[2][0].dependency_id = str(uuid.uuid4())
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert "orphan_dependency" in issue_codes(exc)


def test_duplicate_logical_result_is_rejected():
    sources = source_set()
    duplicate = copy.deepcopy(sources[4][0])
    duplicate.id = str(uuid.uuid4())
    sources[4].append(duplicate)
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert "duplicate_task_result" in issue_codes(exc)


def test_failed_execution_does_not_supply_required_result():
    sources = source_set()
    sources[4][0].state = "failed"
    sources[4][0].output_payload = None
    with pytest.raises(ConsolidationError) as exc:
        build_consolidation(*sources)
    assert "missing_successful_execution" in issue_codes(exc)


class MissingMissionRepository:
    rolled_back = False

    async def mission(self, mission_id, lock=False):
        return None

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_missing_mission_rolls_back_and_raises_not_found():
    repository = MissingMissionRepository()
    with pytest.raises(NotFoundError, match="Mission not found"):
        await ConsolidationService(repository).consolidate(str(uuid.uuid4()))
    assert repository.rolled_back
