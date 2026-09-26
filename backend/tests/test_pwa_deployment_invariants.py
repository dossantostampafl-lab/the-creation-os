from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NGINX_CONFIGS = (
    ROOT / "frontend" / "nginx.conf",
    ROOT / "frontend" / "nginx.render.conf",
)
SECURITY_HEADERS = (
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Content-Security-Policy",
)


def _location(config: str, declaration: str) -> str:
    start = config.index(f"{declaration} {{")
    opening = config.index("{", start)
    depth = 0
    for position in range(opening, len(config)):
        character = config[position]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return config[start : position + 1]
    raise AssertionError(f"unterminated Nginx location: {declaration}")


@pytest.mark.parametrize("config_path", NGINX_CONFIGS, ids=lambda path: path.name)
def test_pwa_resources_have_explicit_safe_cache_policies(config_path: Path) -> None:
    config = config_path.read_text(encoding="utf-8")

    service_worker = _location(config, "location = /sw.js")
    assert 'add_header Cache-Control "no-cache, no-store, must-revalidate" always;' in service_worker
    assert "try_files $uri =404;" in service_worker

    manifest = _location(config, "location = /manifest.webmanifest")
    assert 'default_type "application/manifest+json";' in manifest
    assert 'add_header Cache-Control "public, max-age=3600" always;' in manifest
    assert "try_files $uri =404;" in manifest

    assets = _location(config, "location /assets/")
    assert 'add_header Cache-Control "public, max-age=31536000, immutable" always;' in assets
    assert "try_files $uri =404;" in assets


@pytest.mark.parametrize("config_path", NGINX_CONFIGS, ids=lambda path: path.name)
def test_pwa_locations_preserve_security_headers(config_path: Path) -> None:
    config = config_path.read_text(encoding="utf-8")

    for declaration in ("location = /sw.js", "location = /manifest.webmanifest", "location /assets/"):
        block = _location(config, declaration)
        for header in SECURITY_HEADERS:
            assert f"add_header {header}" in block, f"{config_path.name} {declaration} drops {header} through Nginx inheritance"


@pytest.mark.parametrize("config_path", NGINX_CONFIGS, ids=lambda path: path.name)
def test_spa_navigation_falls_back_to_index(config_path: Path) -> None:
    config = config_path.read_text(encoding="utf-8")
    spa = _location(config, "location /")

    assert "try_files $uri $uri/ /index.html;" in spa
