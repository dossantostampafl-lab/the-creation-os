from enum import StrEnum

from app.core.domain import InvalidStateTransition


class DispatchState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    ACKNOWLEDGED = "acknowledged"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


TRANSITIONS = {
    DispatchState.QUEUED: {DispatchState.LEASED, DispatchState.CANCELLED},
    DispatchState.RETRY_SCHEDULED: {DispatchState.LEASED, DispatchState.CANCELLED},
    DispatchState.LEASED: {DispatchState.ACKNOWLEDGED, DispatchState.RETRY_SCHEDULED, DispatchState.DEAD_LETTERED, DispatchState.QUEUED},
    DispatchState.ACKNOWLEDGED: set(),
    DispatchState.DEAD_LETTERED: set(),
    DispatchState.CANCELLED: set(),
    DispatchState.FAILED: {DispatchState.RETRY_SCHEDULED, DispatchState.DEAD_LETTERED},
}


def transition_dispatch(current: str, target: DispatchState) -> str:
    source = DispatchState(current)
    if target not in TRANSITIONS[source]:
        raise InvalidStateTransition("dispatch", source.value, target.value)
    return target.value


def retry_delay(base_seconds: int, attempt_count: int, maximum_seconds: int) -> int:
    if base_seconds < 1 or attempt_count < 1 or maximum_seconds < 1:
        raise ValueError("Invalid retry policy")
    return min(base_seconds * (2 ** (attempt_count - 1)), maximum_seconds)
