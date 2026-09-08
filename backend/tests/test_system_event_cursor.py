from __future__ import annotations

from app.api.system_state import cursor_resync_reason


def test_cursor_ahead_of_chronicle_requires_resync() -> None:
    reason = cursor_resync_reason(after=10, head=8, first_position=None)
    assert reason == {"status": "RESYNCING", "reason": "cursor_ahead", "expected_max": 8, "received": 10}


def test_gap_after_cursor_requires_resync() -> None:
    reason = cursor_resync_reason(after=5, head=9, first_position=8)
    assert reason == {"status": "RESYNCING", "reason": "gap", "expected": 6, "received": 8}


def test_contiguous_cursor_does_not_resync() -> None:
    assert cursor_resync_reason(after=5, head=9, first_position=6) is None
