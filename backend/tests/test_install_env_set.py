"""env_set must write a secret verbatim, whatever characters it contains.

The original helper substituted through `sed -i "s|^KEY=.*|KEY=$value|"`. A value holding the
expression delimiter closed the `s` command early, so sed aborted with "unknown option to `s'"
and left .env untouched -- a silent no-op that reads as success. These tests run the real helper,
lifted out of install.sh, against values that would break a substitution.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "deploy" / "oracle" / "install.sh"

HOSTILE_VALUES = [
    "sk-ant-api03-" + "a" * 70 + "|" + "b" * 20,  # the delimiter itself
    "pass&word",  # '&' means "the whole match" in a sed replacement
    "back\\slash",
    "with/slash+plus=equals",
    "s|x|y|",
]


def _helpers() -> str:
    """The env_get/env_set definitions as install.sh actually defines them."""
    content = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(r"^env_get\(\).*?^\}$", content, re.MULTILINE | re.DOTALL)
    assert match is not None, "env_get/env_set helpers not found in install.sh"
    return match.group(0)


def test_install_sh_does_not_substitute_values_through_sed() -> None:
    assert "sed -i" not in INSTALL_SH.read_text(encoding="utf-8")


def _run_env_set(tmp_path: Path, initial: str, key: str, value: str) -> str:
    env_file = tmp_path / ".env"
    env_file.write_text(initial, encoding="utf-8")
    script = f"""
set -euo pipefail
cd {tmp_path}
{_helpers()}
env_set "$1" "$2"
"""
    subprocess.run(
        ["bash", "-c", script, "bash", key, value],
        check=True,
        capture_output=True,
    )
    return env_file.read_text(encoding="utf-8")


def test_env_set_replaces_an_existing_line_verbatim(tmp_path: Path) -> None:
    for value in HOSTILE_VALUES:
        result = _run_env_set(
            tmp_path, "APP_ENV=development\nANTHROPIC_API_KEY=\n", "ANTHROPIC_API_KEY", value
        )
        assert f"ANTHROPIC_API_KEY={value}\n" in result
        assert "APP_ENV=development\n" in result
        assert result.count("ANTHROPIC_API_KEY=") == 1


def test_env_set_appends_a_missing_line(tmp_path: Path) -> None:
    result = _run_env_set(tmp_path, "APP_ENV=development\n", "ANTHROPIC_API_KEY", "secret|value")
    assert "ANTHROPIC_API_KEY=secret|value\n" in result
    assert "APP_ENV=development\n" in result


def test_env_set_collapses_duplicate_lines(tmp_path: Path) -> None:
    result = _run_env_set(tmp_path, "K=one\nK=two\nOTHER=keep\n", "K", "three")
    assert result.count("K=") == 1, result  # the two K lines collapse into one
    assert "K=three\n" in result
    assert "OTHER=keep\n" in result


def test_env_set_leaves_other_keys_with_the_same_prefix_alone(tmp_path: Path) -> None:
    result = _run_env_set(tmp_path, "LLM_PROVIDER=fake\nLLM_PROVIDER_EXTRA=keep\n", "LLM_PROVIDER", "anthropic")
    assert "LLM_PROVIDER=anthropic\n" in result
    assert "LLM_PROVIDER_EXTRA=keep\n" in result
