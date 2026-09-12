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
