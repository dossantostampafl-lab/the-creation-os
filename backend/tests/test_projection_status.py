from __future__ import annotations

from app.projections.checkpoints import projection_lag


def test_projection_lag_is_zero_at_head() -> None:
    assert projection_lag(head=12, checkpoint=12) == 0


def test_projection_lag_counts_unapplied_chronicle_positions() -> None:
    assert projection_lag(head=12, checkpoint=9) == 3


def test_projection_lag_rejects_checkpoint_ahead_of_head() -> None:
    try:
        projection_lag(head=9, checkpoint=12)
    except ValueError as exc:
        assert "ahead" in str(exc)
    else:
        raise AssertionError("expected ValueError")
