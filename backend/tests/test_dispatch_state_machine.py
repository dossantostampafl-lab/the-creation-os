import pytest

from app.core.dispatch_state_machine import DispatchState, retry_delay, transition_dispatch
from app.core.domain import InvalidStateTransition


@pytest.mark.parametrize(
    "source,target",
    [
        ("queued", DispatchState.LEASED),
        ("retry_scheduled", DispatchState.LEASED),
        ("leased", DispatchState.ACKNOWLEDGED),
        ("leased", DispatchState.RETRY_SCHEDULED),
        ("leased", DispatchState.DEAD_LETTERED),
        ("queued", DispatchState.CANCELLED),
        ("retry_scheduled", DispatchState.CANCELLED),
        ("leased", DispatchState.QUEUED),
    ],
)
def test_allowed(source, target):
    assert transition_dispatch(source, target) == target.value


@pytest.mark.parametrize(
    "source,target",
    [
        ("acknowledged", DispatchState.LEASED),
        ("dead_lettered", DispatchState.QUEUED),
        ("cancelled", DispatchState.LEASED),
        ("acknowledged", DispatchState.CANCELLED),
    ],
)
def test_forbidden(source, target):
    with pytest.raises(InvalidStateTransition):
        transition_dispatch(source, target)


def test_backoff():
    assert [retry_delay(30, x, 1000) for x in (1, 2, 3)] == [30, 60, 120]


def test_backoff_cap():
    assert retry_delay(30, 10, 300) == 300


@pytest.mark.parametrize("values", [(0, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_invalid_backoff(values):
    with pytest.raises(ValueError):
        retry_delay(*values)
