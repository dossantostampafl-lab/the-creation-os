from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "deploy" / "oracle" / "bootstrap-oracle.sh"
ORACLE_README = REPO_ROOT / "deploy" / "oracle" / "README.md"


def test_oracle_one_command_bootstrap_contract() -> None:
    assert BOOTSTRAP.is_file(), "Oracle one-command bootstrap script is missing"
    content = BOOTSTRAP.read_text(encoding="utf-8")

    assert content.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in content
    assert "dossantostampafl-lab/the-creation-os.git" in content
    assert "git clone" in content
    assert "fetch --prune origin main" in content
    assert "reset --hard origin/main" in content
    assert 'deploy/oracle/install.sh' in content
    assert "LLM_API_KEY=" not in content
    assert "ANTHROPIC_API_KEY=" not in content
    assert "ELEVENLABS_API_KEY=" not in content


def test_oracle_readme_exposes_single_copy_paste_command() -> None:
    content = ORACLE_README.read_text(encoding="utf-8")

    assert "bootstrap-oracle.sh | sudo bash" in content
