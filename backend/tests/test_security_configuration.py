from __future__ import annotations

import pytest
from pydantic.v1 import ValidationError

from app.config import Settings


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "secret_key": "a" * 32,
        "creator_bootstrap_username": "creator",
        "creator_bootstrap_password": "b" * 32,
        "database_url": "postgresql+asyncpg://creation:secret@postgres/db",
        "redis_url": "redis://redis:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_wildcard_cors_with_credentials() -> None:
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS"):
        _production_settings(cors_allow_origins="*")


def test_production_proto_bridge_requires_strong_shared_secret() -> None:
    with pytest.raises(ValidationError, match="PROTO_CREATION_SHARED_SECRET"):
        _production_settings(
            proto_base_url="https://proto.example",
            proto_creation_shared_secret="short-secret",
        )


@pytest.mark.parametrize(("url", "accepted"), [
    ("https://api.provider.example/v1", True),
    ("http://localhost:3001/v1", True),
    ("http://host.docker.internal:3001/v1", True),
    ("http://freellmapi:3001/v1", True),          # a container on the Compose network
    ("http://192.168.1.10:3001/v1", True),        # the private network
    ("http://gateway.example.com/v1", False),     # the key would cross the internet in the clear
    ("http://8.8.8.8/v1", False),
    ("https://user:pass@api.example/v1", False),  # credentials belong in the header, not the URL
    ("ftp://api.example/v1", False),
    ("https://api.example/v1?key=secret", False),
])
def test_a_provider_gateway_must_not_receive_a_key_in_the_clear(url: str, accepted: bool) -> None:
    from app.inference.base_url import checked_base_url

    if accepted:
        assert checked_base_url("PROVIDER_BASE_URL", url) == url
        return
    with pytest.raises(RuntimeError, match="PROVIDER_BASE_URL"):
        checked_base_url("PROVIDER_BASE_URL", url)
