from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import dotenv_values
from pydantic.v1 import BaseSettings, Field, SecretStr, validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
FILE_SECRET_ENV_VARS = {
    "APP_SECRET_KEY": "APP_SECRET_KEY_FILE",
    "CREATOR_BOOTSTRAP_PASSWORD": "CREATOR_BOOTSTRAP_PASSWORD_FILE",
    "DATABASE_URL": "DATABASE_URL_FILE",
    "ELEVENLABS_API_KEY": "ELEVENLABS_API_KEY_FILE",
    "GITHUB_TOKEN": "GITHUB_TOKEN_FILE",
    "LLM_API_KEY": "LLM_API_KEY_FILE",
    "WORKER_CREDENTIAL": "WORKER_CREDENTIAL_FILE",
}


def load_file_secrets() -> None:
    """Load Docker-style *_FILE settings without exposing values as image metadata."""
    dotenv = dotenv_values(ENV_FILE)
    for environment_name, file_environment_name in FILE_SECRET_ENV_VARS.items():
        if environment_name in os.environ:
            continue
        configured_path = os.getenv(file_environment_name) or dotenv.get(file_environment_name)
        if not configured_path:
            continue
        secret_path = Path(configured_path)
        if not secret_path.is_absolute():
            secret_path = PROJECT_ROOT / secret_path
        try:
            os.environ[environment_name] = secret_path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise RuntimeError(f"Unable to read secret file configured by {file_environment_name}") from exc


load_file_secrets()


class Settings(BaseSettings):
    app_env: str = Field(..., env="APP_ENV")
    secret_key: SecretStr = Field(..., env="APP_SECRET_KEY")
    creator_bootstrap_username: str = Field(..., env="CREATOR_BOOTSTRAP_USERNAME")
    creator_bootstrap_password: SecretStr = Field(..., env="CREATOR_BOOTSTRAP_PASSWORD")
    sovereign_creator_id: str | None = Field(None, env="SOVEREIGN_CREATOR_ID")
    # Comma-separated list of allowed browser origins for CORSMiddleware
    # (app/main.py). Optional here — validated below to be mandatory when
    # app_env == "production" (no silent fallback to a wildcard) — with a
    # Python-level default covering the real local frontend dev origin
    # (frontend/vite.config.ts's configured port 5173) when unset outside
    # production. See ARCHITECTURE.md, Lote: CORS por ambiente + rate
    # limiting no login.
    cors_allowed_origins: str | None = Field(None, env="CORS_ALLOWED_ORIGINS")
    access_token_expire_minutes: int = Field(15, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(1440, env="REFRESH_TOKEN_EXPIRE_MINUTES")
    # Login rate limiting (app/auth/routes.py) — a single-Creator system, so
    # this is about friction against automated guessing, not throughput.
    login_rate_limit_attempts: int = Field(10, env="LOGIN_RATE_LIMIT_ATTEMPTS")
    login_rate_limit_window_seconds: int = Field(60, env="LOGIN_RATE_LIMIT_WINDOW_SECONDS")
    database_url: str = Field(..., env="DATABASE_URL")
    redis_url: str = Field(..., env="REDIS_URL")
    worker_credential: SecretStr | None = Field(None, env="WORKER_CREDENTIAL")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    llm_provider: str = Field("fake", env="LLM_PROVIDER")
    llm_model: str = Field("fake", env="LLM_MODEL")
    llm_api_key: SecretStr | None = Field(None, env="LLM_API_KEY")
    embedding_provider: str = Field("fake", env="EMBEDDING_PROVIDER")
    embedding_model: str = Field("fake", env="EMBEDDING_MODEL")
    # Was named chronicle_embedding_dim and never bound to an env var or read
    # anywhere (dead constant since it was first added) — Chronicles don't use
    # embeddings at all; this is conscious_memory's vector dimension, renamed
    # and given a real env binding for Lote 2.5. FakeEmbeddingModel.embed()
    # always returns 8 floats, so this must stay 8 unless embedding_provider
    # is also switched to a real provider with a matching dimension.
    conscious_memory_embedding_dim: int = Field(8, env="CONSCIOUS_MEMORY_EMBEDDING_DIM")
    opportunity_min_score: float = Field(0.45, env="OPPORTUNITY_MIN_SCORE")
    opportunity_min_source_reliability: float = Field(0.5, env="OPPORTUNITY_MIN_SOURCE_RELIABILITY")
    opportunity_expiration_hours: int = Field(72, env="OPPORTUNITY_EXPIRATION_HOURS")
    opportunity_min_evidence: int = Field(1, env="OPPORTUNITY_MIN_EVIDENCE")
    opportunity_enabled_universes: str = Field("finance,technology,business", env="OPPORTUNITY_ENABLED_UNIVERSES")
    perception_enabled: bool = Field(True, env="PERCEPTION_ENABLED")
    perception_min_interval_seconds: int = Field(300, env="PERCEPTION_MIN_INTERVAL_SECONDS")
    perception_default_interval_seconds: int = Field(900, env="PERCEPTION_DEFAULT_INTERVAL_SECONDS")
    perception_request_timeout_seconds: int = Field(10, env="PERCEPTION_REQUEST_TIMEOUT_SECONDS")
    perception_max_retries: int = Field(2, env="PERCEPTION_MAX_RETRIES")
    perception_failure_threshold: int = Field(5, env="PERCEPTION_FAILURE_THRESHOLD")
    perception_suspend_seconds: int = Field(1800, env="PERCEPTION_SUSPEND_SECONDS")
    perception_financial_symbols: str = Field("AAPL", env="PERCEPTION_FINANCIAL_SYMBOLS")
    perception_technology_repositories: str = Field("openai/openai-python", env="PERCEPTION_TECHNOLOGY_REPOSITORIES")
    perception_enabled_universes: str = Field("finance,technology", env="PERCEPTION_ENABLED_UNIVERSES")
    perception_allowed_hosts: str = Field("query1.finance.yahoo.com,api.github.com", env="PERCEPTION_ALLOWED_HOSTS")
    opportunity_notification_min_score: float = Field(0.70, env="OPPORTUNITY_NOTIFICATION_MIN_SCORE")
    opportunity_notification_min_confidence: float = Field(0.65, env="OPPORTUNITY_NOTIFICATION_MIN_CONFIDENCE")
    opportunity_notification_max_risk: float = Field(0.80, env="OPPORTUNITY_NOTIFICATION_MAX_RISK")
    opportunity_notification_cooldown_seconds: int = Field(21600, env="OPPORTUNITY_NOTIFICATION_COOLDOWN_SECONDS")
    elevenlabs_enabled: bool = Field(False, env="ELEVENLABS_ENABLED")
    elevenlabs_api_key: SecretStr | None = Field(None, env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("configured-voice-id", env="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field("eleven_multilingual_v2", env="ELEVENLABS_MODEL_ID")
    elevenlabs_timeout_seconds: float = Field(12.0, env="ELEVENLABS_TIMEOUT_SECONDS")
    voice_synthesis_max_chars: int = Field(1200, env="VOICE_SYNTHESIS_MAX_CHARS")

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"

    @property
    def access_token_expires(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expires(self) -> timedelta:
        return timedelta(minutes=self.refresh_token_expire_minutes)

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        if not self.cors_allowed_origins:
            # Only reachable outside production — validate_cors_allowed_origins
            # below requires a real value in production. Matches the confirmed
            # real local dev origin (frontend/vite.config.ts: server.port =
            # 5173; docker-compose.yml maps the frontend container's Nginx to
            # host port 5173 too) — both host forms, since browsers treat
            # localhost and 127.0.0.1 as distinct origins.
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @validator("app_env")
    def validate_env(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        return value

    @validator("cors_allowed_origins", always=True)
    def validate_cors_allowed_origins(cls, value: str | None, values: dict) -> str | None:
        if values.get("app_env") == "production" and not value:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must be set in production — no silent fallback to a "
                "permissive default. Set it to the real deployed frontend origin(s), comma-separated."
            )
        return value


def resolve_cors_middleware_kwargs(origins: list[str]) -> dict:
    """allow_credentials must never coexist with a literal wildcard origin —
    if "*" is present, degrade to no-credentials instead of allowing the
    dangerous combination silently. A pure function (no FastAPI/Settings
    dependency) specifically so this rule is unit-testable on its own,
    independent of the app's one-time import-time CORSMiddleware wiring
    in app/main.py."""
    return {
        "allow_origins": origins,
        "allow_credentials": "*" not in origins,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


# Instantiated from environment at runtime; mypy flags missing constructor args.
# This is intentional for BaseSettings which reads from env vars.
settings = Settings()  # type: ignore[call-arg]
