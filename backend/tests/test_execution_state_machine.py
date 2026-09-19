import pytest

from app.agents.state_machine import TERMINAL_STATES, TRANSITIONS, ExecutionState, transition_execution
from app.core.domain import InvalidStateTransition


def test_all_allowed_execution_transitions():
    expected = {
        ("pending", "accepted"),
        ("accepted", "running"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "timed_out"),
        ("pending", "cancelled"),
        ("accepted", "cancelled"),
    }
    assert {(source.value, target.value) for source, targets in TRANSITIONS.items() for target in targets} == expected
    for source, target in expected:
        assert transition_execution(source, ExecutionState(target)) == target


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "cancelled", "timed_out"])
def test_terminal_states_reject_every_transition(terminal):
    assert ExecutionState(terminal) in TERMINAL_STATES
    for target in ExecutionState:
        with pytest.raises(InvalidStateTransition):
            transition_execution(terminal, target)


def test_non_terminal_invalid_transitions_are_rejected():
    for source in (ExecutionState.PENDING, ExecutionState.ACCEPTED, ExecutionState.RUNNING):
        for target in ExecutionState:
            if target not in TRANSITIONS[source]:
                with pytest.raises(InvalidStateTransition):
                    transition_execution(source.value, target)
