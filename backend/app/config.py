from __future__ import annotations

import os
from datetime import timedelta
from urllib.parse import urlsplit

from pydantic.v1 import BaseSettings, Field, SecretStr, validator


class Settings(BaseSettings):
    app_env: str = Field(..., env="APP_ENV")
    secret_key: SecretStr = Field(..., env="APP_SECRET_KEY")
    creator_bootstrap_username: str = Field(..., env="CREATOR_BOOTSTRAP_USERNAME")
    creator_bootstrap_password: SecretStr = Field(..., env="CREATOR_BOOTSTRAP_PASSWORD")
    sovereign_creator_id: str | None = Field(None, env="SOVEREIGN_CREATOR_ID")
    access_token_expire_minutes: int = Field(15, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(1440, env="REFRESH_TOKEN_EXPIRE_MINUTES")
    login_max_failures: int = Field(10, env="LOGIN_MAX_FAILURES")
    login_failure_window_seconds: int = Field(300, env="LOGIN_FAILURE_WINDOW_SECONDS")
    database_url: str = Field(..., env="DATABASE_URL")
    redis_url: str = Field(..., env="REDIS_URL")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    cors_allow_origins: str = Field("", env="CORS_ALLOW_ORIGINS")
    llm_provider: str = Field("fake", env="LLM_PROVIDER")
    llm_model: str = Field("fake", env="LLM_MODEL")
    llm_api_key: SecretStr | None = Field(None, env="LLM_API_KEY")
    embedding_provider: str = Field("fake", env="EMBEDDING_PROVIDER")
    embedding_model: str = Field("fake", env="EMBEDDING_MODEL")
    proto_base_url: str | None = Field(None, env="PROTO_BASE_URL")
    proto_creation_shared_secret: SecretStr | None = Field(
        None,
        env="PROTO_CREATION_SHARED_SECRET",
    )
    proto_timeout_seconds: float = Field(10.0, gt=0.0, le=60.0, env="PROTO_TIMEOUT_SECONDS")
    chronicle_embedding_dim: int = 8

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        env_file_encoding = "utf-8"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def access_token_expires(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expires(self) -> timedelta:
        return timedelta(minutes=self.refresh_token_expire_minutes)

    @property
    def proto_bridge_configured(self) -> bool:
        return bool(self.proto_base_url and self.proto_creation_shared_secret)

    @validator("app_env")
    def validate_env(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        return value

    @validator("proto_base_url")
    def validate_proto_base_url(cls, value: str | None, values: dict[str, object]) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("PROTO_BASE_URL must be an absolute HTTP(S) origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("PROTO_BASE_URL must not contain credentials, query, or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("PROTO_BASE_URL must be an origin without a path")
        if values.get("app_env") == "production" and parsed.scheme != "https":
            raise ValueError("PROTO_BASE_URL must use HTTPS in production")
        return normalized


# Instantiated from environment at runtime; mypy flags missing constructor args.
# This is intentional for BaseSettings which reads from env vars.
settings = Settings()  # type: ignore[call-arg]
