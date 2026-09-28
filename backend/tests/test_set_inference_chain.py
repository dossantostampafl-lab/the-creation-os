"""set-inference.sh against a scratch installation: what it writes, and when it must refuse.

The chain matters because the API refuses to start when any provider in it lacks its key or model,
so a script that wrote FreeLLMAPI-first with an unconfigured reserve would take the server down.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY = "freellmapi-TESTKEY-0123456789"


def _fake(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def server(tmp_path: Path):
    root = tmp_path / "srv"
    (root / "deploy" / "oracle").mkdir(parents=True)
    for name in ("set-inference.sh", "env-file.sh"):
        shutil.copy(REPO_ROOT / "deploy" / "oracle" / name, root / "deploy" / "oracle" / name)
    (root / "docker-compose.yml").write_text("services: {}\n")
    (root / "docker-compose.cloud.yml").write_text("services: {}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(bin_dir, "id", "echo 0")  # the script insists on root
    _fake(bin_dir, "docker", "echo docker \"$@\" >> \"$DOCKER_LOG\"")
    _fake(bin_dir, "curl", "exit 0")  # health check passes at once; the login answer is empty
    env_path = root / ".env"
    env_path.write_text(
        "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-ant-EXISTING\nANTHROPIC_MODEL=claude-sonnet-5\n"
        "CREATOR_BOOTSTRAP_USERNAME=creator\nCREATOR_BOOTSTRAP_PASSWORD=pw\n"
    )

    def run(*args: str, **extra: str) -> subprocess.CompletedProcess:
        environment = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "DOCKER_LOG": str(tmp_path / "docker.log"),
            **extra,
        }
        return subprocess.run(["bash", str(root / "deploy" / "oracle" / "set-inference.sh"), *args],
                              cwd=root, env=environment, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def env() -> dict[str, str]:
        pairs = (line.split("=", 1) for line in env_path.read_text().splitlines() if "=" in line)
        return {key: value for key, value in pairs}

    return run, env, root


def test_freellmapi_first_with_claude_as_the_reserve(server):
    run, env, root = server
    result = run("freellmapi", "auto", FREELLMAPI_API_KEY=KEY, FALLBACK_PROVIDERS="anthropic")
    assert result.returncode == 0, result.stderr
    values = env()
    assert values["LLM_PROVIDER"] == "freellmapi"
    assert values["LLM_FALLBACK_PROVIDERS"] == "anthropic"
    assert values["FREELLMAPI_MODEL"] == "auto" and values["FREELLMAPI_API_KEY"] == KEY
    assert values["FREELLMAPI_BASE_URL"] == "http://host.docker.internal:3001/v1"
    # The reserve's credentials are left exactly as they were.
    assert values["ANTHROPIC_API_KEY"] == "sk-ant-EXISTING" and values["ANTHROPIC_MODEL"] == "claude-sonnet-5"
    assert KEY not in result.stdout + result.stderr, "the key must never be echoed"
    assert (root / ".env.bak").exists()


def test_it_refuses_and_changes_nothing_when_the_reserve_is_not_configured(server):
    run, env, root = server
    text = (root / ".env").read_text().replace("ANTHROPIC_API_KEY=sk-ant-EXISTING\n", "")
    (root / ".env").write_text(text)
    before = (root / ".env").read_text()
    result = run("freellmapi", "auto", FREELLMAPI_API_KEY=KEY, FALLBACK_PROVIDERS="anthropic")
    assert result.returncode != 0
    assert "ANTHROPIC_API_KEY" in result.stderr and "Nothing was changed" in result.stderr
    assert (root / ".env").read_text() == before and not (root / ".env.bak").exists()


@pytest.mark.parametrize("fallback", ["fake", "freellmapi", "anthropic,nonsense"])
def test_it_refuses_a_bad_reserve_chain(server, fallback):
    run, env, root = server
    before = (root / ".env").read_text()
    result = run("freellmapi", "auto", FREELLMAPI_API_KEY=KEY, FALLBACK_PROVIDERS=fallback)
    assert result.returncode != 0 and "Nothing was changed" in result.stderr
    assert (root / ".env").read_text() == before


@pytest.mark.parametrize("url", ["ftp://host/v1", "http://user:pw@host/v1", "http://host/v1 ; rm -rf /"])
def test_it_refuses_an_unsafe_freellmapi_address(server, url):
    run, env, root = server
    before = (root / ".env").read_text()
    result = run("freellmapi", "auto", FREELLMAPI_API_KEY=KEY, FALLBACK_PROVIDERS="anthropic", FREELLMAPI_BASE_URL=url)
    assert result.returncode != 0 and (root / ".env").read_text() == before


def test_switching_back_to_one_provider_clears_the_reserve(server):
    run, env, root = server
    assert run("freellmapi", "auto", FREELLMAPI_API_KEY=KEY, FALLBACK_PROVIDERS="anthropic").returncode == 0
    result = run("anthropic", "claude-sonnet-5")
    assert result.returncode == 0, result.stderr
    values = env()
    assert values["LLM_PROVIDER"] == "anthropic" and values["LLM_FALLBACK_PROVIDERS"] == ""


def test_the_key_already_in_env_is_kept_when_none_is_given(server):
    run, env, root = server
    assert run("freellmapi", "auto", FREELLMAPI_API_KEY=KEY, FALLBACK_PROVIDERS="anthropic").returncode == 0
    result = run("freellmapi", "auto", FALLBACK_PROVIDERS="anthropic")
    assert result.returncode == 0 and env()["FREELLMAPI_API_KEY"] == KEY


def test_freellmapi_can_be_set_up_without_a_key_but_other_providers_cannot(server):
    run, env, root = server
    result = run("freellmapi", "auto", FALLBACK_PROVIDERS="anthropic")
    assert result.returncode == 0, result.stderr
    values = env()
    assert values["LLM_PROVIDER"] == "freellmapi" and values["FREELLMAPI_API_KEY"] == ""
    assert "no Authorization header" in result.stdout
    # The reserve is unaffected, and another provider without any key is still refused.
    assert values["ANTHROPIC_API_KEY"] == "sk-ant-EXISTING"
    text = (root / ".env").read_text().replace("ANTHROPIC_API_KEY=sk-ant-EXISTING\n", "")
    (root / ".env").write_text(text)
    refused = run("anthropic", "claude-sonnet-5")
    assert refused.returncode != 0 and "nothing changed" in refused.stderr


def test_a_freellmapi_reserve_needs_only_its_model(server):
    run, env, root = server
    (root / ".env").write_text((root / ".env").read_text() + "FREELLMAPI_MODEL=auto\n")
    result = run("anthropic", "claude-sonnet-5", ANTHROPIC_API_KEY="sk-ant-NEW", FALLBACK_PROVIDERS="freellmapi")
    assert result.returncode == 0, result.stderr
    assert env()["LLM_FALLBACK_PROVIDERS"] == "freellmapi"
