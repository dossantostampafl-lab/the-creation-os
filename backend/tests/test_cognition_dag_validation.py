from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.cognition.contracts import MissionPlanCandidate, MissionStepCandidate


def make_step(key: str, position: int, depends_on: list[str] | None = None) -> MissionStepCandidate:
    return MissionStepCandidate(
        step_key=key,
        title=key,
        description=f"Execute {key}",
        universe="engineering",
        position=position,
        depends_on=depends_on or [],
    )


def test_plan_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError, match="unknown mission step dependencies"):
        MissionPlanCandidate(strategy="invalid", steps=[make_step("a", 1, ["missing"])])


def test_plan_rejects_dependency_cycle() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        MissionPlanCandidate(
            strategy="invalid",
            steps=[make_step("a", 1, ["b"]), make_step("b", 2, ["a"])],
        )
