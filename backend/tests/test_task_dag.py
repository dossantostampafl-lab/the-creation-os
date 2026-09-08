from __future__ import annotations

from app.kernel.task_dag import ready_step_keys


def test_root_steps_are_ready_first() -> None:
    dependencies = {"a": set(), "b": {"a"}, "c": {"a"}}
    assert ready_step_keys(dependencies, succeeded=set(), terminal=set()) == ["a"]


def test_dependents_become_ready_after_dependencies_succeed() -> None:
    dependencies = {"a": set(), "b": {"a"}, "c": {"a"}}
    assert ready_step_keys(dependencies, succeeded={"a"}, terminal={"a"}) == ["b", "c"]


def test_failed_dependency_never_unlocks_dependent_step() -> None:
    dependencies = {"a": set(), "b": {"a"}}
    assert ready_step_keys(dependencies, succeeded=set(), terminal={"a"}) == []
