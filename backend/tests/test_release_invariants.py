from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"


def test_production_compose_exposes_only_frontend_and_keeps_state_services_internal() -> None:
    content = PROD_COMPOSE.read_text(encoding="utf-8")

    assert '${CREATION_HTTP_PORT:-8080}:8080' in content
    assert '"5432:5432"' not in content
    assert '"6379:6379"' not in content
    assert "internal: true" in content
    assert "./backend:/app" not in content
    assert "APP_ENV: production" in content


def test_production_compose_requires_provider_configuration_and_never_uses_openai_alias() -> None:
    content = PROD_COMPOSE.read_text(encoding="utf-8")

    assert "LLM_API_KEY: ${LLM_API_KEY:?LLM_API_KEY is required}" in content
    assert "LLM_MODEL: ${LLM_MODEL:?LLM_MODEL is required}" in content
    assert "EMBEDDING_MODEL: ${EMBEDDING_MODEL:?EMBEDDING_MODEL is required}" in content
    assert "OPENAI_API_KEY:" not in content
    assert "LLM_PROVIDER: ${LLM_PROVIDER:-openai}" in content
    assert "EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:-openai}" in content


def test_production_services_are_read_only_and_prevent_privilege_escalation() -> None:
    content = PROD_COMPOSE.read_text(encoding="utf-8")

    assert content.count("read_only: true") >= 3
    assert content.count("no-new-privileges:true") >= 2
