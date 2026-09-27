"""The deploy workflow reaches a live server, so what it must never do is worth pinning.

Each assertion here stands for a way this could hand the server to someone: a trigger that is
not a person pressing a button, a token that can write, a third-party action that receives the
SSH key, a secret placed where the server's process list shows it, or an input that reaches a
remote shell unchecked.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["deploy"]["steps"]


def test_only_a_person_can_start_it() -> None:
    # yaml reads a bare `on:` key as the boolean True.
    triggers = _workflow()[True]
    assert set(triggers) == {"workflow_dispatch"}, "a push must not be able to reach the server"


def test_the_token_cannot_write() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}


def test_two_runs_cannot_overlap() -> None:
    concurrency = _workflow()["concurrency"]
    assert concurrency["group"] == "deploy-oracle"
    assert concurrency["cancel-in-progress"] is False


def test_no_third_party_action_handles_the_credentials() -> None:
    for step in _steps():
        uses = step.get("uses")
        if uses is not None:
            assert uses.startswith("actions/"), f"third-party action in the deploy path: {uses}"


def test_the_key_is_never_an_argument_to_ssh() -> None:
    """An argument is visible in the server's process list while the command runs."""
    text = WORKFLOW.read_text(encoding="utf-8")
    ssh_line_start = text.index("| ssh -i")
    ssh_invocation = text[ssh_line_start : text.index("\n\n", ssh_line_start)]
    assert "ANTHROPIC_API_KEY" not in ssh_invocation or "read -r ANTHROPIC_API_KEY" in ssh_invocation
    # It arrives on stdin instead, read as a single line before the script runs.
    assert "IFS= read -r ANTHROPIC_API_KEY" in text


def test_the_key_never_goes_through_a_substitution() -> None:
    """A key holding the expression's delimiter breaks sed silently; see env-file.sh."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("sed -e \"s/${ANTHROPIC_API_KEY", "sed \"s/${ANTHROPIC_API_KEY", "sed -i"):
        assert forbidden not in text


def test_the_key_is_masked_before_anything_can_print_it() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "::add-mask::" in text or "IFS= read -r ANTHROPIC_API_KEY" in text


def test_the_ref_input_is_validated_before_it_reaches_a_shell() -> None:
    validation = _steps()[0]["run"]
    assert "^[A-Za-z0-9._/-]*$" in validation, "the ref must be held to git ref characters"


def test_the_private_key_is_removed_from_the_runner() -> None:
    cleanup = _steps()[-1]
    assert cleanup.get("if") == "always()"
    assert "rm -f ~/.ssh/id_deploy" in cleanup["run"]


def test_the_host_key_can_be_pinned() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "DEPLOY_SSH_HOST_KEY" in text
    assert "StrictHostKeyChecking=no" not in text, "never accept any host key"
