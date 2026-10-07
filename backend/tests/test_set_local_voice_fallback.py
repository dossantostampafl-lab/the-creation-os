"""set-local-voice.sh promotes freellmapi to primary without leaving it in the reserve chain."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path: Path, env_text: str) -> dict[str, str]:
    root = tmp_path / "srv"
    (root / "deploy" / "oracle").mkdir(parents=True)
    for name in ("set-local-voice.sh", "env-file.sh"):
        shutil.copy(REPO_ROOT / "deploy" / "oracle" / name, root / "deploy" / "oracle" / name)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(bin_dir, "id", "echo 0")
    _fake(bin_dir, "docker", "exit 0")
    _fake(bin_dir, "curl", "exit 0")
    env_path = root / ".env"
    env_path.write_text(env_text, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(root / "deploy" / "oracle" / "set-local-voice.sh")],
        cwd=root,
        env={"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    pairs = (line.split("=", 1) for line in env_path.read_text().splitlines() if "=" in line)
    return {key: value for key, value in pairs}


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("freellmapi", ""),
        ("anthropic,freellmapi", "anthropic"),
        (" FreeLLMAPI , openai_compatible ", "openai_compatible"),
        ("anthropic", "anthropic"),
    ],
)
def test_freellmapi_is_removed_from_the_preserved_reserve(tmp_path: Path, before: str, after: str) -> None:
    values = _run(tmp_path, f"LLM_PROVIDER=anthropic\nLLM_FALLBACK_PROVIDERS={before}\n")
    assert values["LLM_PROVIDER"] == "freellmapi"
    assert values["LLM_FALLBACK_PROVIDERS"] == after
    Settings(_env_file=None, llm_provider="freellmapi", llm_fallback_providers=after)


def test_anthropic_reserve_is_used_when_only_freellmapi_was_preserved(tmp_path: Path) -> None:
    values = _run(
        tmp_path,
        "LLM_PROVIDER=anthropic\nLLM_FALLBACK_PROVIDERS=freellmapi\n"
        "ANTHROPIC_API_KEY=sk-ant-TEST\nANTHROPIC_MODEL=claude-sonnet-5\n",
    )
    assert values["LLM_FALLBACK_PROVIDERS"] == "anthropic"
    Settings(_env_file=None, llm_provider="freellmapi", llm_fallback_providers="anthropic")
