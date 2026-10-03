from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "proxy" / "proxy.py"
spec = importlib.util.spec_from_file_location("range_proxy", MODULE)
assert spec and spec.loader
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.parametrize(
    ("host", "port", "listen"),
    [
        ("juice-shop", "3000", "3000"),
        ("webgoat", "8080", "8080"),
        ("webgoat", "9090", "9090"),
    ],
)
def test_proxy_accepts_only_declared_range_destinations(host, port, listen):
    config = proxy.config_from_env({
        "TARGET_HOST": host,
        "TARGET_PORT": port,
        "LISTEN_PORT": listen,
    })
    assert config.target_host == host
    assert config.target_port == int(port)


@pytest.mark.parametrize(
    "env",
    [
        {"TARGET_HOST": "example.com", "TARGET_PORT": "443", "LISTEN_PORT": "3000"},
        {"TARGET_HOST": "host.docker.internal", "TARGET_PORT": "7070", "LISTEN_PORT": "3000"},
        {"TARGET_HOST": "juice-shop", "TARGET_PORT": "22", "LISTEN_PORT": "3000"},
        {"TARGET_HOST": "juice-shop", "TARGET_PORT": "3000", "LISTEN_PORT": "0"},
        {},
    ],
)
def test_proxy_rejects_arbitrary_or_invalid_destinations(env):
    with pytest.raises(ValueError):
        proxy.config_from_env(env)
