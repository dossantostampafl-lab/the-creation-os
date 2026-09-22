from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"


def _service_block(text: str, service: str, next_service: str | None) -> str:
    start = text.index(f"  {service}:\n")
    if next_service is None:
        return text[start:]
    end = text.index(f"  {next_service}:\n", start + 1)
    return text[start:end]


def test_local_and_cloud_runtimes_are_both_available() -> None:
    assert COMPOSE.is_file()
    assert (ROOT / "docker-compose.prod.yml").is_file()
    assert (ROOT / "render.yaml").is_file()
    assert (ROOT / "frontend" / "Dockerfile.render").is_file()
    assert (ROOT / "frontend" / "nginx.render.conf").is_file()


def test_only_frontend_is_exposed_to_the_lan() -> None:
    text = COMPOSE.read_text()
    frontend = _service_block(text, "frontend", "api")
    api = _service_block(text, "api", "postgres")
    postgres = _service_block(text, "postgres", "redis")
    redis = _service_block(text, "redis", "worker")

    assert '"0.0.0.0:${CREATION_HTTP_PORT:-8080}:8080"' in frontend
    assert '"127.0.0.1:${CREATION_API_PORT:-8000}:8000"' in api
    assert "\n    ports:" not in postgres
    assert "\n    ports:" not in redis


def test_proto_bridge_is_disabled_by_default() -> None:
    text = COMPOSE.read_text()
    assert "PROTO_BASE_URL: ${PROTO_BASE_URL:-}" in text
    assert "PROTO_CREATION_SHARED_SECRET: ${PROTO_CREATION_SHARED_SECRET:-}" in text
    assert "local-creation-proto-bridge-change-me" not in text


def test_local_runtime_has_persistent_data_and_restart_policy() -> None:
    text = COMPOSE.read_text()
    assert "postgres_data:/var/lib/postgresql/data" in text
    assert "redis_data:/data" in text
    assert text.count("restart: unless-stopped") >= 5


def test_windows_local_ops_scripts_exist() -> None:
    scripts = ROOT / "scripts"
    assert (scripts / "local-start.ps1").is_file()
    assert (scripts / "local-status.ps1").is_file()
    assert (scripts / "local-stop.ps1").is_file()
