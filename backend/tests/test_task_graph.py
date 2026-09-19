import pytest

from app.core.domain import InvalidStateTransition
from app.core.task_graph import TaskState, topological_order, transition_task


def test_task_state_machine():
    assert transition_task("created", TaskState.PLANNED) == "planned"
    assert transition_task("planned", TaskState.READY) == "ready"
    assert transition_task("ready", TaskState.COMPLETED) == "completed"


def test_invalid_and_cancelled_transitions():
    assert transition_task("created", TaskState.CANCELLED) == "cancelled"
    with pytest.raises(InvalidStateTransition):
        transition_task("cancelled", TaskState.READY)


def test_topological_sort_dag():
    assert topological_order({"a", "b", "c"}, {("b", "a"), ("c", "b")}) == ["a", "b", "c"]


def test_cycle_detection():
    with pytest.raises(ValueError, match="cycle"):
        topological_order({"a", "b"}, {("a", "b"), ("b", "a")})


def test_self_dependency_rejected():
    with pytest.raises(ValueError):
        topological_order({"a"}, {("a", "a")})


def test_orphan_dependency_rejected():
    with pytest.raises(ValueError):
        topological_order({"a"}, {("a", "missing")})
