from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_render_blueprint_exists() -> None:
    assert (ROOT / "render.yaml").is_file()


def test_render_blueprint_defines_required_services() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "creation-api" in text
    assert "creation-worker" in text
    assert "creation-frontend" in text
    assert "creation-redis" in text
    assert "creation-postgres" in text
    assert "type: web" in text
    assert "type: worker" in text
    assert "type: keyvalue" in text


def test_render_api_uses_port_health_and_migration_contract() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "preDeployCommand: python -m alembic upgrade head" in text
    assert "--host 0.0.0.0" in text
    assert "${PORT:-10000}" in text
    assert "/api/v1/health/ready" in text


def test_render_frontend_is_not_bound_to_compose_dns() -> None:
    text = (ROOT / "frontend" / "nginx.render.conf").read_text()
    assert "api:8000" not in text
    assert "127.0.0.11" not in text
    assert "listen 10000" in text
    assert "location /" in text
    assert "try_files $uri $uri/ /index.html" in text


def test_render_frontend_build_requires_explicit_api_url() -> None:
    text = (ROOT / "frontend" / "Dockerfile.render").read_text()
    assert "ARG VITE_API_BASE_URL" in text
    assert 'RUN test -n "$VITE_API_BASE_URL"' in text
    assert "EXPOSE 10000" in text


def test_render_blueprint_has_no_fake_production_defaults() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "LLM_PROVIDER: fake" not in text
    assert "EMBEDDING_PROVIDER: fake" not in text


def test_render_blueprint_uses_managed_data_references() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "fromDatabase" in text
    assert "fromService" in text
    assert "property: connectionString" in text


def test_render_worker_is_background_only() -> None:
    text = (ROOT / "render.yaml").read_text()
    worker_block = text.split("name: creation-worker", 1)[1].split("name: creation-frontend", 1)[0]
    assert "type: worker" in worker_block
    assert "healthCheckPath" not in worker_block


def test_render_blueprint_does_not_embed_local_service_urls() -> None:
    text = (ROOT / "render.yaml").read_text()
    assert "localhost" not in text
    assert "postgres:5432" not in text
    assert "redis:6379" not in text
