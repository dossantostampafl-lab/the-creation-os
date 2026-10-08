"""Sites other projects append to deploy/Caddyfile must survive a deploy."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deploy" / "oracle" / "keep-caddy-sites.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
BOOTSTRAP = REPO_ROOT / "deploy" / "oracle" / "bootstrap-oracle.sh"

STAR_TREK_BLOCK = (
    "# >>> star-trek-1 (gerado por deploy/oracle/setup-docker.sh — não edite entre as marcas)\n"
    "startrek.1-2-3-4.sslip.io {\n"
    "\treverse_proxy star-trek-1:8787\n"
    "}\n"
    "# <<< star-trek-1\n"
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _server_checkout(tmp_path: Path) -> Path:
    """A checkout on main with a newer Caddyfile waiting on origin/next."""
    repo = tmp_path / "the-creation-os"
    (repo / "deploy" / "oracle").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "deploy" / "oracle" / SCRIPT.name)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "deploy" / "Caddyfile").write_text("{$CREATION_DOMAIN} {\n\treverse_proxy frontend:8080\n}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "checkout", "-qb", "next")
    (repo / "deploy" / "Caddyfile").write_text("{$CREATION_DOMAIN} {\n\tencode gzip\n\treverse_proxy frontend:8080\n}\n")
    _git(repo, "commit", "-qam", "v2")
    _git(repo, "checkout", "-q", "main")
    with (repo / "deploy" / "Caddyfile").open("a") as caddyfile:
        caddyfile.write("\n" + STAR_TREK_BLOCK)
    return repo


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "deploy/oracle/keep-caddy-sites.sh", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CADDY_BACKUP_DIR": str(repo.parent / "backups")},
    )


def test_update_keeps_the_star_trek_block_and_still_fast_forwards(tmp_path: Path) -> None:
    repo = _server_checkout(tmp_path)
    caddyfile = repo / "deploy" / "Caddyfile"
    inode = caddyfile.stat().st_ino

    result = _run(repo, "next")
    assert result.returncode == 0, result.stderr
    assert "sites kept from other projects: 1" in result.stdout

    _git(repo, "merge", "--ff-only", "next")
    content = caddyfile.read_text()
    assert content.startswith("{$CREATION_DOMAIN} {\n\tencode gzip\n")
    assert content.endswith(STAR_TREK_BLOCK)
    assert content.count("# >>> star-trek-1") == 1
    # The Caddy container mounts this one file; a replaced file would be invisible to it.
    assert caddyfile.stat().st_ino == inode


def test_running_twice_does_not_duplicate_the_block(tmp_path: Path) -> None:
    repo = _server_checkout(tmp_path)
    assert _run(repo, "next").returncode == 0
    first = (repo / "deploy" / "Caddyfile").read_text()
    assert _run(repo, "next").returncode == 0
    assert (repo / "deploy" / "Caddyfile").read_text() == first


def test_restore_puts_the_block_back_after_a_hard_reset(tmp_path: Path) -> None:
    repo = _server_checkout(tmp_path)
    saved = tmp_path / "saved-Caddyfile"
    shutil.copy(repo / "deploy" / "Caddyfile", saved)
    _git(repo, "reset", "-q", "--hard", "next")
    assert STAR_TREK_BLOCK not in (repo / "deploy" / "Caddyfile").read_text()

    result = _run(repo, "--restore", str(saved))
    assert result.returncode == 0, result.stderr
    assert (repo / "deploy" / "Caddyfile").read_text().endswith(STAR_TREK_BLOCK)


def test_deploy_and_bootstrap_run_it_before_touching_tracked_files() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    keep = workflow.index('keep-caddy-sites.sh "origin/$target"')
    assert workflow.index("deploy/oracle deploy/stf\n") < keep < workflow.index('sudo git merge --ff-only "origin/$target"')

    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert bootstrap.index("caddy_copy") < bootstrap.index("reset --hard origin/main")
    assert "keep-caddy-sites.sh --restore" in bootstrap
