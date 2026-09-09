from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
NGINX_CONFIG = REPO_ROOT / "frontend" / "nginx.conf"


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


def test_production_database_url_is_supplied_separately_from_literal_postgres_password() -> None:
    content = _content()

    assert "DATABASE_URL: ${DATABASE_URL:?DATABASE_URL is required}" in content
    assert "postgresql+asyncpg://creation:${POSTGRES_PASSWORD" not in content


def test_production_compose_passes_current_multi_provider_configuration_without_broken_local_defaults() -> None:
    content = _content()

    required = {
        "LLM_MODEL: ${LLM_MODEL:-}",
        "LLM_API_KEY: ${LLM_API_KEY:-}",
        "FREELLMAPI_API_KEY: ${FREELLMAPI_API_KEY:-}",
        "FREELLMAPI_MODEL: ${FREELLMAPI_MODEL:-}",
        "FREELLMAPI_BASE_URL: ${FREELLMAPI_BASE_URL:-}",
        "OPENAI_COMPATIBLE_API_KEY: ${OPENAI_COMPATIBLE_API_KEY:-}",
        "OPENAI_COMPATIBLE_MODEL: ${OPENAI_COMPATIBLE_MODEL:-}",
        "OPENAI_COMPATIBLE_BASE_URL: ${OPENAI_COMPATIBLE_BASE_URL:-}",
    }
    assert required <= {line.strip() for line in content.splitlines()}
    assert "http://freellmapi:3001/v1" not in content
    assert "http://ollama:11434/v1" not in content


def test_worker_has_outbound_network_path_for_hosted_inference_providers() -> None:
    content = _content()
    worker_block = content.split("  worker:\n", 1)[1].split("\n  postgres:\n", 1)[0]

    assert "      - edge" in worker_block
    assert "      - internal" in worker_block


def test_frontend_proxy_uses_docker_runtime_dns_resolution() -> None:
    content = NGINX_CONFIG.read_text(encoding="utf-8")

    assert "resolver 127.0.0.11" in content
    assert "set $api_upstream http://api:8000;" in content
    assert "proxy_pass $api_upstream;" in content


def test_production_services_are_read_only_and_prevent_privilege_escalation() -> None:
    content = _content()

    assert content.count("read_only: true") >= 3
    assert content.count("no-new-privileges:true") >= 2
