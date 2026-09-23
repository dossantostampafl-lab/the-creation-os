from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
NGINX_CONFIG = REPO_ROOT / "frontend" / "nginx.conf"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
KERNEL_API = REPO_ROOT / "backend" / "app" / "api" / "kernel.py"


def test_local_compose_runs_complete_product_stack() -> None:
    content = LOCAL_COMPOSE.read_text(encoding="utf-8")
    frontend_block = content.split("  frontend:\n", 1)[1].split("\n  api:\n", 1)[0]

    assert '"0.0.0.0:${CREATION_HTTP_PORT:-8080}:8080"' in frontend_block
    assert "context: ./frontend" in frontend_block
    assert "VITE_API_BASE_URL: /api/v1" in frontend_block
    assert "condition: service_healthy" in frontend_block


def test_frontend_proxy_uses_docker_runtime_dns_resolution() -> None:
    content = NGINX_CONFIG.read_text(encoding="utf-8")

    assert "resolver 127.0.0.11" in content
    assert "set $api_upstream http://api:8000;" in content
    assert "proxy_pass $api_upstream;" in content


def test_ci_uses_read_only_repository_token() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read\n" in content


def test_frontend_nginx_configs_apply_browser_security_headers() -> None:
    required = {
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header X-Frame-Options "DENY" always;',
        'add_header Referrer-Policy "no-referrer" always;',
        # The microphone is allowed for this origin only, so the Creator can speak to DEUS.
        'add_header Permissions-Policy "camera=(), microphone=(self), geolocation=(), payment=(), usb=()" always;',
        "add_header Content-Security-Policy",
        "server_tokens off;",
    }
    content = NGINX_CONFIG.read_text(encoding="utf-8")
    for expected in required:
        assert expected in content, f"{NGINX_CONFIG.name} missing {expected}"


def test_manifestation_has_no_direct_creator_api_bypass() -> None:
    content = KERNEL_API.read_text(encoding="utf-8")

    assert '@router.post("/missions/{entity_id}/manifest"' not in content
