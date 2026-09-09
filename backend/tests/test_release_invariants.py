from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"


def _content() -> str:
    return PROD_COMPOSE.read_text(encoding="utf-8")


def test_production_compose_exposes_only_frontend_and_keeps_state_services_internal() -> None:
    content = _content()

    assert '${CREATION_HTTP_PORT:-8080}:8080' in content
    assert '"5432:5432"' not in content
    assert '"6379:6379"' not in content
    assert "internal: true" in content
    assert "./backend:/app" not in content
    assert "./frontend:/app" not in content
    assert "APP_ENV: production" in content


def test_production_compose_requires_explicit_operational_provider_selection() -> None:
    content = _content()

    assert "LLM_PROVIDER: ${LLM_PROVIDER:?LLM_PROVIDER is required}" in content
    assert "EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:?EMBEDDING_PROVIDER is required}" in content
    assert "EMBEDDING_MODEL: ${EMBEDDING_MODEL:?EMBEDDING_MODEL is required}" in content
    assert "LLM_PROVIDER: fake" not in content
    assert "EMBEDDING_PROVIDER: fake" not in content
    assert "OPENAI_API_KEY:" not in content


def test_production_compose_passes_current_multi_provider_configuration_without_secrets() -> None:
    content = _content()

    required = {
        "LLM_MODEL: ${LLM_MODEL:-}",
        "LLM_API_KEY: ${LLM_API_KEY:-}",
        "FREELLMAPI_API_KEY: ${FREELLMAPI_API_KEY:-}",
        "FREELLMAPI_MODEL: ${FREELLMAPI_MODEL:-}",
        "FREELLMAPI_BASE_URL: ${FREELLMAPI_BASE_URL:-http://freellmapi:3001/v1}",
        "OPENAI_COMPATIBLE_API_KEY: ${OPENAI_COMPATIBLE_API_KEY:-}",
        "OPENAI_COMPATIBLE_MODEL: ${OPENAI_COMPATIBLE_MODEL:-}",
        "OPENAI_COMPATIBLE_BASE_URL: ${OPENAI_COMPATIBLE_BASE_URL:-http://ollama:11434/v1}",
    }
    assert required <= set(content.splitlines()) | {line.strip() for line in content.splitlines()}


def test_production_services_are_read_only_and_prevent_privilege_escalation() -> None:
    content = _content()

    assert content.count("read_only: true") >= 3
    assert content.count("no-new-privileges:true") >= 2
