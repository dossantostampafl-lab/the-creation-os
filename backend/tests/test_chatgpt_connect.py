from __future__ import annotations

from pathlib import Path

from app.inference.chatgpt_connect import _default_credentials_path


def test_default_chatgpt_credentials_path_stays_outside_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    path = _default_credentials_path()

    assert path == tmp_path / ".config" / "the-creation-os" / "chatgpt" / "credentials.json"
    assert path.is_absolute()
