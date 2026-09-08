from __future__ import annotations

from app.projections.refresher import needs_refresh


def test_missing_checkpoint_requires_refresh() -> None:
    assert needs_refresh(head=0, checkpoint=None) is True


def test_lagging_checkpoint_requires_refresh() -> None:
    assert needs_refresh(head=8, checkpoint=7) is True


def test_current_checkpoint_does_not_refresh() -> None:
    assert needs_refresh(head=8, checkpoint=8) is False
