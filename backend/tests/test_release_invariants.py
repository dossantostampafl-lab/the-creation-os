from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
RENDER_BLUEPRINT = REPO_ROOT / "render.yaml"
NGINX_CONFIG = REPO_ROOT / "frontend" / "nginx.conf"
NGINX_RENDER_CONFIG = REPO_ROOT / "frontend" / "nginx.render.conf"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _content() -> str:
    return PROD_COMPOSE.read_text(encoding="utf-8")


def test_local_compose_runs_complete_product_stack() -> None:
    content = LOCAL_COMPOSE.read_text(encoding="utf-8")
    frontend_block = content.split("  frontend:\n", 1)[1].split("\n  api:\n", 1)[0]

    assert '"8080:8080"' in frontend_block
    assert "context: ./frontend" in frontend_block
    assert "VITE_API_BASE_URL: /api/v1" in frontend_block
    assert "condition: service_healthy" in frontend_block


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


def test_production_worker_receives_optional_proto_bridge_configuration() -> None:
    content = _content()
    render = RENDER_BLUEPRINT.read_text(encoding="utf-8")

    required_compose = {
        "PROTO_BASE_URL: ${PROTO_BASE_URL:-}",
        "PROTO_CREATION_SHARED_SECRET: ${PROTO_CREATION_SHARED_SECRET:-}",
        "PROTO_TIMEOUT_SECONDS: ${PROTO_TIMEOUT_SECONDS:-10}",
    }
    assert required_compose <= {line.strip() for line in content.splitlines()}
    assert render.count("- key: PROTO_BASE_URL") == 2
    assert render.count("- key: PROTO_CREATION_SHARED_SECRET") == 2
    assert render.count("- key: PROTO_TIMEOUT_SECONDS") == 2
    assert "envVarKey: PROTO_BASE_URL" in render
    assert "envVarKey: PROTO_CREATION_SHARED_SECRET" in render


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


def test_ci_uses_read_only_repository_token() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read\n" in content


def test_frontend_nginx_configs_apply_browser_security_headers() -> None:
    required = {
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header X-Frame-Options "DENY" always;',
        'add_header Referrer-Policy "no-referrer" always;',
        'add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()" always;',
        "add_header Content-Security-Policy",
        "server_tokens off;",
    }
    for path in (NGINX_CONFIG, NGINX_RENDER_CONFIG):
        content = path.read_text(encoding="utf-8")
        for expected in required:
            assert expected in content, f"{path.name} missing {expected}"
