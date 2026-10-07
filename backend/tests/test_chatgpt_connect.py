from __future__ import annotations

from pathlib import Path

import pytest

from app.inference.chatgpt_connect import (
    _default_credentials_path,
    _granted_scopes,
    _inside_git_checkout,
    _load_or_create_host_id,
)


def test_default_chatgpt_credentials_path_stays_outside_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    path = _default_credentials_path()

    assert path == tmp_path / ".config" / "the-creation-os" / "chatgpt" / "profiles" / "default" / "credentials.json"
    assert path.is_absolute()


def test_chatgpt_host_id_is_persisted_before_credentials_exist(tmp_path: Path) -> None:
    output = tmp_path / "credentials.json"

    first = _load_or_create_host_id(output, {})
    second = _load_or_create_host_id(output, {})

    assert first.startswith("urn:uuid:")
    assert second == first
    assert (tmp_path / "host-id").read_text(encoding="utf-8").strip() == first


def test_saved_remote_profile_does_not_overwrite_the_browser_hosts_identity(tmp_path: Path) -> None:
    output = tmp_path / "credentials.json"
    local_host_id = _load_or_create_host_id(output, {})
    remote_host_id = "urn:uuid:11111111-1111-4111-8111-111111111111"
    credentials = {"ext_agent_host_id": remote_host_id}

    selected_host_id = _load_or_create_host_id(output, credentials)

    assert selected_host_id == remote_host_id
    assert (tmp_path / "host-id").read_text(encoding="utf-8").strip() == local_host_id


def test_plan_permission_comes_only_from_token_response_scopes() -> None:
    assert _granted_scopes({"scope": "openid profile chatgpt.tokens.use.direct"}) == {
        "openid",
        "profile",
        "chatgpt.tokens.use.direct",
    }

    with pytest.raises(RuntimeError, match="did not return granted scopes"):
        _granted_scopes({})


def test_credentials_destination_inside_git_checkout_is_rejected_by_guard(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()

    assert _inside_git_checkout(checkout / "credentials.json")
    assert not _inside_git_checkout(tmp_path / "outside" / "credentials.json")
