from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class PlannedStep(Protocol):
    step_key: str
    position: int
    depends_on: list[str]


def validate_mission_steps(steps: Sequence[PlannedStep]) -> None:
    """Reject a Mission plan whose steps do not form a well-defined dependency DAG."""
    keys = [step.step_key for step in steps]
    if len(keys) != len(set(keys)):
        raise ValueError("mission step keys must be unique")
    positions = [step.position for step in steps]
    if len(positions) != len(set(positions)):
        raise ValueError("mission step positions must be unique")
    dependencies = {step.step_key: set(step.depends_on) for step in steps}
    known = set(keys)
    for key, deps in dependencies.items():
        if key in deps:
            raise ValueError("mission step cannot depend on itself")
        missing = deps - known
        if missing:
            raise ValueError(f"unknown mission step dependencies: {sorted(missing)}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("mission plan dependency cycle detected")
        if key in visited:
            return
        visiting.add(key)
        for dependency in dependencies[key]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in keys:
        visit(key)
