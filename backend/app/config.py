from __future__ import annotations

import os
from datetime import timedelta
from urllib.parse import urlsplit

from pydantic.v1 import BaseSettings, Field, SecretStr, validator

SUPPORTED_LLM_PROVIDERS = frozenset({"openai", "anthropic", "freellmapi", "openai_compatible"})

# The values .env.example ships. They are published, so they are not credentials anywhere.
PLACEHOLDER_SECRETS = frozenset({"replace-me-with-a-secure-random-value", "change-me-securely"})


def _split_providers(value: str) -> list[str]:
    return [name.strip().lower() for name in value.split(",") if name.strip()]


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
    llm_fallback_providers: str = Field("", env="LLM_FALLBACK_PROVIDERS")
    llm_model: str = Field("fake", env="LLM_MODEL")
    llm_api_key: SecretStr | None = Field(None, env="LLM_API_KEY")
    embedding_provider: str = Field("fake", env="EMBEDDING_PROVIDER")
    embedding_model: str = Field("fake", env="EMBEDDING_MODEL")
    semantic_cache_mode: str = Field("shadow", env="SEMANTIC_CACHE_MODE")
    semantic_cache_policy_version: str = Field("sc-v1", env="SEMANTIC_CACHE_POLICY_VERSION")
    semantic_cache_embedding_version: str = Field("v1", env="SEMANTIC_CACHE_EMBEDDING_VERSION")
    semantic_cache_redis_prefix: str = Field("tco:semantic-cache", env="SEMANTIC_CACHE_REDIS_PREFIX")
    semantic_cache_similarity_threshold: float = Field(0.94, ge=0.0, le=1.0, env="SEMANTIC_CACHE_SIMILARITY_THRESHOLD")
    semantic_cache_revalidate_threshold: float = Field(0.90, ge=0.0, le=1.0, env="SEMANTIC_CACHE_REVALIDATE_THRESHOLD")
    semantic_cache_max_candidates: int = Field(5, ge=1, le=50, env="SEMANTIC_CACHE_MAX_CANDIDATES")
    semantic_cache_ttl_seconds: int = Field(86400, ge=1, env="SEMANTIC_CACHE_TTL_SECONDS")
    semantic_cache_document_ttl_seconds: int = Field(3600, ge=1, env="SEMANTIC_CACHE_DOCUMENT_TTL_SECONDS")
    semantic_cache_deterministic_ttl_seconds: int = Field(3600, ge=1, env="SEMANTIC_CACHE_DETERMINISTIC_TTL_SECONDS")
    semantic_cache_lock_seconds: int = Field(30, ge=1, le=300, env="SEMANTIC_CACHE_LOCK_SECONDS")
    semantic_cache_singleflight_wait_ms: int = Field(250, ge=0, le=5000, env="SEMANTIC_CACHE_SINGLEFLIGHT_WAIT_MS")
    trinity_enabled: bool = Field(True, env="TRINITY_ENABLED")
    trinity_min_confidence: float = Field(0.7, ge=0.0, le=1.0, env="TRINITY_MIN_CONFIDENCE")
    workspace_root: str = Field("/var/lib/creation/workspaces", env="WORKSPACE_ROOT")
    workspace_max_bytes: int = Field(1_000_000, ge=1, env="WORKSPACE_MAX_BYTES")
    web_capability_enabled: bool = Field(True, env="WEB_CAPABILITY_ENABLED")
    web_timeout_seconds: float = Field(15.0, gt=0.0, env="WEB_TIMEOUT_SECONDS")
    web_max_bytes: int = Field(500_000, ge=1, env="WEB_MAX_BYTES")
    proto_base_url: str | None = Field(None, env="PROTO_BASE_URL")
    proto_creation_shared_secret: SecretStr | None = Field(None, env="PROTO_CREATION_SHARED_SECRET")
    proto_timeout_seconds: float = Field(10.0, gt=0.0, le=60.0, env="PROTO_TIMEOUT_SECONDS")
    elevenlabs_enabled: bool = Field(False, env="ELEVENLABS_ENABLED")
    elevenlabs_api_key: SecretStr | None = Field(None, env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("configured-voice-id", env="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field("eleven_multilingual_v2", env="ELEVENLABS_MODEL_ID")
    elevenlabs_timeout_seconds: float = Field(12.0, env="ELEVENLABS_TIMEOUT_SECONDS")
    voice_synthesis_max_chars: int = Field(1200, env="VOICE_SYNTHESIS_MAX_CHARS")
    chronicle_embedding_dim: int = 8

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        env_file_encoding = "utf-8"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def inference_provider_chain(self) -> list[str]:
        """Configured provider followed by the declared fallbacks, in order."""
        chain = [self.llm_provider.strip().lower()]
        chain.extend(
            name
            for name in _split_providers(self.llm_fallback_providers)
            if name not in chain
        )
        return chain

    @property
    def access_token_expires(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expires(self) -> timedelta:
        return timedelta(minutes=self.refresh_token_expire_minutes)

    @property
    def proto_bridge_configured(self) -> bool:
        configured_value = self.proto_creation_shared_secret
        return bool(
            self.proto_base_url
            and configured_value is not None
            and configured_value.get_secret_value().strip()
        )

    @validator("secret_key")
    def validate_secret_key(cls, value: SecretStr, values: dict[str, object]) -> SecretStr:
        raw = value.get_secret_value()
        # This key signs every access and refresh token, so in production it must be a real
        # secret: the example value is published, and a short one is guessable.
        if values.get("app_env") == "production":
            if raw in PLACEHOLDER_SECRETS:
                raise ValueError("APP_SECRET_KEY is still the published example value; generate a new one")
            if len(raw) < 32:
                raise ValueError("APP_SECRET_KEY must be at least 32 characters in production")
        return value

    @validator("creator_bootstrap_password")
    def validate_creator_bootstrap_password(cls, value: SecretStr, values: dict[str, object]) -> SecretStr:
        if values.get("app_env") == "production" and value.get_secret_value() in PLACEHOLDER_SECRETS:
            raise ValueError("CREATOR_BOOTSTRAP_PASSWORD is still the published example value")
        return value

    @validator("app_env")
    def validate_env(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        return value

    @validator("llm_fallback_providers")
    def validate_llm_fallback_providers(cls, value: str, values: dict[str, object]) -> str:
        names = _split_providers(value)
        if "fake" in names:
            raise ValueError("LLM_FALLBACK_PROVIDERS must not contain fake")
        unsupported = [name for name in names if name not in SUPPORTED_LLM_PROVIDERS]
        if unsupported:
            raise ValueError(
                "LLM_FALLBACK_PROVIDERS must list supported providers: "
                + ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
            )
        if len(set(names)) != len(names):
            raise ValueError("LLM_FALLBACK_PROVIDERS must not repeat a provider")
        primary = str(values.get("llm_provider", "")).strip().lower()
        if primary in names:
            raise ValueError("LLM_FALLBACK_PROVIDERS must not repeat LLM_PROVIDER")
        return ",".join(names)

    @validator("semantic_cache_mode")
    def validate_semantic_cache_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"off", "shadow", "exact", "semantic"}:
            raise ValueError("SEMANTIC_CACHE_MODE must be off, shadow, exact, or semantic")
        return normalized

    @validator("semantic_cache_revalidate_threshold")
    def validate_semantic_cache_threshold_order(cls, value: float, values: dict[str, object]) -> float:
        raw_hit_threshold = values.get("semantic_cache_similarity_threshold", 0.94)
        hit_threshold = (
            float(raw_hit_threshold)
            if isinstance(raw_hit_threshold, (int, float, str))
            else 0.94
        )
        if value > hit_threshold:
            raise ValueError("SEMANTIC_CACHE_REVALIDATE_THRESHOLD must be <= SEMANTIC_CACHE_SIMILARITY_THRESHOLD")
        return value

    @validator("semantic_cache_policy_version", "semantic_cache_embedding_version", "semantic_cache_redis_prefix")
    def validate_semantic_cache_nonempty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("semantic cache version and prefix values must not be empty")
        return normalized

    @validator("cors_allow_origins")
    def validate_cors_allow_origins(cls, value: str, values: dict[str, object]) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if values.get("app_env") == "production" and "*" in origins:
            raise ValueError("CORS_ALLOW_ORIGINS must not contain wildcard in production")
        return ",".join(origins)

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

    @validator("proto_creation_shared_secret")
    def validate_proto_credential(
        cls,
        value: SecretStr | None,
        values: dict[str, object],
    ) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value().strip()
        if not raw:
            return None
        if values.get("app_env") == "production" and len(raw) < 32:
            raise ValueError("PROTO_CREATION_SHARED_SECRET must be at least 32 characters in production")
        return SecretStr(raw)


settings = Settings()  # type: ignore[call-arg]
