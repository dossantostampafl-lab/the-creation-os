from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.mission import MissionPlanRequest


def step(key: str, position: int, depends_on: list[str] | None = None) -> dict:
    return {
        "step_key": key,
        "title": key.title(),
        "description": f"Execute {key}",
        "universe": "engineering",
        "position": position,
        "depends_on": depends_on or [],
        "completion_criteria": {"done": True},
    }


def test_mission_plan_requires_structured_steps() -> None:
    plan = MissionPlanRequest(
        strategy="deterministic",
        steps=[step("contracts", 1), step("runtime", 2, ["contracts"])],
        completion_criteria={"gate_a": True},
    )

    assert plan.steps[1].depends_on == ["contracts"]


def test_mission_plan_rejects_dependency_cycles() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        MissionPlanRequest(
            strategy="invalid",
            steps=[step("a", 1, ["b"]), step("b", 2, ["a"])],
        )
