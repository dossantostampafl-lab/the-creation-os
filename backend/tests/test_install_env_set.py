"""env_set must write a secret verbatim, whatever characters it contains.

The original helper substituted through `sed -i "s|^KEY=.*|KEY=$value|"`. A value holding the
expression delimiter closed the `s` command early, so sed aborted with "unknown option to `s'"
and left .env untouched -- a silent no-op that reads as success. These tests run the real helper,
lifted out of install.sh, against values that would break a substitution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "deploy" / "oracle" / "install.sh"
ENV_FILE_SH = REPO_ROOT / "deploy" / "oracle" / "env-file.sh"
SET_INFERENCE_SH = REPO_ROOT / "deploy" / "oracle" / "set-inference.sh"

HOSTILE_VALUES = [
    "sk-ant-api03-" + "a" * 70 + "|" + "b" * 20,  # the delimiter itself
    "pass&word",  # '&' means "the whole match" in a sed replacement
    "back\\slash",
    "with/slash+plus=equals",
    "s|x|y|",
]


def _helpers() -> str:
    """The env_get/env_set definitions, as the deploy scripts actually source them."""
    return ENV_FILE_SH.read_text(encoding="utf-8")


def test_no_deploy_script_substitutes_values_through_sed() -> None:
    for script in (INSTALL_SH, ENV_FILE_SH, SET_INFERENCE_SH):
        assert "sed -i" not in script.read_text(encoding="utf-8"), script.name


def test_both_scripts_share_one_env_helper() -> None:
    for script in (INSTALL_SH, SET_INFERENCE_SH):
        content = script.read_text(encoding="utf-8")
        assert "deploy/oracle/env-file.sh" in content, script.name
        assert "env_set()" not in content, f"{script.name} redefines env_set"


def test_set_inference_never_echoes_the_key() -> None:
    content = SET_INFERENCE_SH.read_text(encoding="utf-8")
    # -s turns the terminal echo off; -r keeps a backslash in the key intact.
    assert "read -rsp" in content
    assert "unset api_key" in content
    # The key is only ever reported as a length or as "<set>", never printed back.
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("echo", "printf")):
            assert "$api_key" not in stripped or "${#api_key}" in stripped, stripped
    # Nothing reads the variable again once it has been cleared.
    after_unset = content.split("unset api_key", 1)[1]
    assert "api_key" not in after_unset


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
