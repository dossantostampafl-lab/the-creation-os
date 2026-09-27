"""tidy-server.sh moves a checkout aside; it must never remove one, and never the live one.

The danger it exists to remove is subtle: Compose takes its project name from the directory's
name, and every checkout of this project is named the-creation-os. A command run in a dormant
copy therefore acts on the live project -- the same containers, the same volumes. Renaming the
dormant directory gives it a project name of its own, which is what makes the mistake harmless.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TIDY = REPO_ROOT / "deploy" / "oracle" / "tidy-server.sh"


def test_it_never_removes_anything() -> None:
    """Parking is a rename. A delete here could take a database with it."""
    script = TIDY.read_text(encoding="utf-8")
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for destructive in ("rm -rf", "rm -r ", "docker volume rm", "down -v", "prune"):
            assert destructive not in stripped, stripped


def _server(tmp_path: Path, *, live: str = "live", dormant: str = "dormant") -> dict[str, Path]:
    live_dir = tmp_path / live
    dormant_dir = tmp_path / dormant
    binaries = tmp_path / "bin"
    references = tmp_path / "ref"
    for directory in (live_dir, dormant_dir, binaries, references):
        directory.mkdir(parents=True)
    (live_dir / "docker-compose.cloud.yml").touch()
    (dormant_dir / "docker-compose.cloud.yml").touch()

    (binaries / "docker").write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        ' *"filter label"*) echo abc123;;\n'
        f' *"project.working_dir"*) echo "{live_dir}";;\n'
        " *'\"com.docker.compose.project\"'*) echo the-creation-os;;\n"
        ' *"volume ls"*) echo the-creation-os_postgres_data;;\n'
        "esac\n"
    )
    (binaries / "find").write_text(
        f'#!/bin/sh\necho "{live_dir}/docker-compose.cloud.yml"\necho "{dormant_dir}/docker-compose.cloud.yml"\n'
    )
    for name in ("docker", "find"):
        (binaries / name).chmod(0o755)
    return {"live": live_dir, "dormant": dormant_dir, "bin": binaries, "ref": references}


def _run(server: dict[str, Path], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(TIDY), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{server['bin']}:{os.environ['PATH']}",
            "TIDY_REFERENCE_PATHS": str(server["ref"]),
            "HOME": str(server["bin"].parent),
        },
    )


def test_the_report_moves_nothing(tmp_path: Path) -> None:
    server = _server(tmp_path)
    result = _run(server)
    assert "Report only" in result.stdout
    assert server["dormant"].is_dir()


def test_parking_renames_the_dormant_checkout_and_keeps_its_contents(tmp_path: Path) -> None:
    server = _server(tmp_path)
    (server["dormant"] / ".env").write_text("LLM_PROVIDER=fake\n")

    _run(server, "--park")

    assert not server["dormant"].exists()
    assert server["live"].is_dir(), "the live installation must never be touched"
    parked = list(tmp_path.glob("dormant.parked-*"))
    assert len(parked) == 1
    assert (parked[0] / ".env").read_text() == "LLM_PROVIDER=fake\n"
    assert "To undo" in (parked[0] / "PARKED.md").read_text()


def test_a_checkout_something_else_starts_is_left_alone(tmp_path: Path) -> None:
    server = _server(tmp_path)
    (server["ref"] / "tco.service").write_text(f"[Service]\nWorkingDirectory={server['dormant']}\n")

    result = _run(server, "--park")

    assert "stays: it is referenced by" in result.stdout
    assert server["dormant"].is_dir()


def test_nothing_is_parked_when_no_container_says_which_is_live(tmp_path: Path) -> None:
    """Without knowing which installation serves, every one of them has to be left alone."""
    server = _server(tmp_path)
    (server["bin"] / "docker").write_text("#!/bin/sh\nexit 0\n")
    (server["bin"] / "docker").chmod(0o755)

    result = _run(server, "--park")

    assert "No api container is running" in result.stdout
    assert server["dormant"].is_dir()
    assert server["live"].is_dir()


@pytest.mark.parametrize("flag", ["", "--park"])
def test_the_live_installation_is_never_parked(tmp_path: Path, flag: str) -> None:
    server = _server(tmp_path)
    _run(server, *([flag] if flag else []))
    assert server["live"].is_dir()
    assert not list(tmp_path.glob("live.parked-*"))
