from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "deploy" / "oracle" / "bootstrap-oracle.sh"
ORACLE_README = REPO_ROOT / "deploy" / "oracle" / "README.md"
OPERATIONS = REPO_ROOT / "docs" / "OPERACAO.md"
ROOT_README = REPO_ROOT / "README.md"


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


def test_oracle_operations_use_the_canonical_install_directory() -> None:
    content = OPERATIONS.read_text(encoding="utf-8")

    assert "/opt/the-creation-os" in content
    assert "~/the-creation-os" not in content


def test_root_readme_lists_oracle_as_a_supported_deployment() -> None:
    content = ROOT_README.read_text(encoding="utf-8")

    assert "### (b) Oracle Cloud" in content


def test_operations_runbook_uses_env_set_for_manual_secret_changes() -> None:
    content = OPERATIONS.read_text(encoding="utf-8")
    section = content.split("### Trocar qualquer outro valor", 1)[1].split("## Comandos administrativos", 1)[0]

    assert "source deploy/oracle/env-file.sh" in section
    assert "env_set" in section
    assert "grep -vE" not in section
    assert "tee -a" not in section


def test_operations_runbook_requires_the_canonical_deploy_path_secret() -> None:
    content = OPERATIONS.read_text(encoding="utf-8")
    deploy_repo_row = next(line for line in content.splitlines() if "`DEPLOY_REPO_DIR`" in line)

    assert "recomendado" in deploy_repo_row
    assert "`/opt/the-creation-os`" in deploy_repo_row
