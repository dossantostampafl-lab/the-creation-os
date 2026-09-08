from __future__ import annotations


class DistributionError(ValueError):
    pass


def validate_distribution(*, mission_status: str, step_count: int) -> None:
    if mission_status.lower() != "authorized":
        raise DistributionError("Mission must be AUTHORIZED before distribution")
    if step_count < 1:
        raise DistributionError("Mission plan must contain executable steps")
