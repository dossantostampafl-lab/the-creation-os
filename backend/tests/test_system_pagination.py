import pytest

from app.projections.system import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, page_window


def test_page_window_defaults_are_bounded() -> None:
    assert page_window() == (DEFAULT_PAGE_SIZE, 0)
    assert page_window(limit=100, offset=200) == (100, 200)


@pytest.mark.parametrize("limit", [0, -1, MAX_PAGE_SIZE + 1])
def test_page_window_rejects_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        page_window(limit=limit)


def test_page_window_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="offset"):
        page_window(offset=-1)
