"""The deploy workflow reaches a live server, so what it must never do is worth pinning.

Each assertion here stands for a way this could hand the server to someone: a trigger that is
not a person pressing a button, a token that can write, a third-party action that receives the
SSH key, a secret placed where the server's process list shows it, or an input that reaches a
remote shell unchecked.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"



_SINGLE_QUOTED = re.compile(r"'[^']*'")
_DOUBLE_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SUBSTITUTION = re.compile(r"\$\((.*?)\)")
_GIT_INVOCATION = re.compile(r"(?:^|[;&|]|\$\(|\bthen\b|\bdo\b|!)\s*git\s")


def _command_positions(line: str) -> list[str]:
    """Every part of a line a shell would run as a command, as its own string.

    A message may mention git without running it, and a command substitution runs inside double
    quotes -- `target="$(git ...)"` is a git call, so each substitution is pulled out whole
    rather than folded back into the line, where the leading `target=` would hide it.
    """
    without_literals = _SINGLE_QUOTED.sub("", line)
    commands = _SUBSTITUTION.findall(without_literals)
    commands.append(_DOUBLE_QUOTED.sub("", without_literals))
    return commands


def _runs_git_unprivileged(line: str) -> bool:
    if "sudo git " in line:
        return False
    return any(_GIT_INVOCATION.search(command) for command in _command_positions(line))


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


def _run_validation(ref: str) -> int:
    """The real validation step, run as the workflow runs it."""
    script = _steps()[0]["run"]
    completed = subprocess.run(
        ["bash", "-e", "-c", script],
        env={"PATH": os.environ["PATH"], "SSH_KEY": "k", "HOST": "h", "REF": ref},
        capture_output=True,
        text=True,
    )
    return completed.returncode


def test_the_default_empty_ref_is_accepted() -> None:
    """An earlier version piped the ref to grep, which emits no line for an empty string and
    so rejected the workflow's own default."""
    assert _run_validation("") == 0


@pytest.mark.parametrize("ref", ["main", "claude/quefo-riar-dashboard-1tkypb", "v1.2.3", "a_b-c.d/e"])
def test_a_real_ref_is_accepted(ref: str) -> None:
    assert _run_validation(ref) == 0


@pytest.mark.parametrize(
    "ref",
    [
        "main'; rm -rf /; echo '",
        "main$(id)",
        "main`whoami`",
        "main; cat /etc/shadow",
        "main && curl evil.invalid",
        "main\nsecond-line",
        "main $(echo hi)",
    ],
)
def test_an_injection_through_the_ref_is_refused(ref: str) -> None:
    """The ref ends up inside a command string the server's shell runs."""
    assert _run_validation(ref) == 1


def test_the_private_key_is_removed_from_the_runner() -> None:
    cleanup = _steps()[-1]
    assert cleanup.get("if") == "always()"
    assert "rm -f ~/.ssh/id_deploy" in cleanup["run"]


def test_the_host_key_can_be_pinned() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "DEPLOY_SSH_HOST_KEY" in text
    assert "StrictHostKeyChecking=no" not in text, "never accept any host key"


def _remote_script() -> str:
    """The script the server runs, as the heredoc in the task step carries it."""
    run = _steps()[2]["run"]
    body = run.split("cat <<'REMOTE'\n", 1)[1]
    return body.split("\nREMOTE\n", 1)[0]


def test_every_git_call_on_the_server_runs_as_root() -> None:
    """An installation cloned by bootstrap-oracle.sh belongs to root. git run as anyone else
    refuses it as dubious ownership and exits 128, which under pipefail ends the run with
    nothing said."""
    offenders = []
    for number, line in enumerate(_remote_script().splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _runs_git_unprivileged(stripped):
            offenders.append(f"{number}: {stripped}")
    assert not offenders, "git without sudo on the server:\n" + "\n".join(offenders)


def test_the_server_script_says_why_it_stops() -> None:
    """A bare exit 128 from git is unreadable on a phone; the run must name the cause."""
    assert "is not a git repository" in _remote_script()


def test_the_git_check_catches_a_call_that_lost_its_sudo() -> None:
    """The check is only worth having if it fails on the line that took a real run down."""
    assert _runs_git_unprivileged('target="$(git symbolic-ref --short refs/remotes/origin/HEAD)"')
    assert _runs_git_unprivileged("git fetch --prune origin")
    assert _runs_git_unprivileged("if ! git rev-parse --git-dir; then")
    # And quiet on the shapes that are not a git call.
    assert not _runs_git_unprivileged('echo "$(pwd) is not a git repository" >&2')
    assert not _runs_git_unprivileged("sudo git fetch --prune origin")
    assert not _runs_git_unprivileged("""target="$(sudo git symbolic-ref --short HEAD)\"""")
