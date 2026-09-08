from __future__ import annotations

import pytest

from app.kernel.distributor import DistributionError, validate_distribution


def test_distribution_requires_authorized_mission() -> None:
    with pytest.raises(DistributionError, match="AUTHORIZED"):
        validate_distribution(mission_status="validated", step_count=1)


def test_distribution_requires_executable_steps() -> None:
    with pytest.raises(DistributionError, match="steps"):
        validate_distribution(mission_status="authorized", step_count=0)


def test_authorized_plan_with_steps_is_distributable() -> None:
    validate_distribution(mission_status="authorized", step_count=2)
