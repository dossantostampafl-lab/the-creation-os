from enum import StrEnum

from app.core.domain import InvalidStateTransition


class ExecutionState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TRANSITIONS = {
    ExecutionState.PENDING: {ExecutionState.ACCEPTED, ExecutionState.CANCELLED},
    ExecutionState.ACCEPTED: {ExecutionState.RUNNING, ExecutionState.CANCELLED},
    ExecutionState.RUNNING: {ExecutionState.SUCCEEDED, ExecutionState.FAILED, ExecutionState.TIMED_OUT},
    ExecutionState.SUCCEEDED: set(),
    ExecutionState.FAILED: set(),
    ExecutionState.CANCELLED: set(),
    ExecutionState.TIMED_OUT: set(),
}

TERMINAL_STATES = frozenset(
    {ExecutionState.SUCCEEDED, ExecutionState.FAILED, ExecutionState.CANCELLED, ExecutionState.TIMED_OUT}
)


def transition_execution(current: str, target: ExecutionState) -> str:
    source = ExecutionState(current)
    if target not in TRANSITIONS[source]:
        raise InvalidStateTransition("agent_execution", source.value, target.value)
    return target.value
