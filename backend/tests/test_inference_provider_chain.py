from __future__ import annotations

import pytest
from pydantic.v1 import ValidationError

from app.config import Settings, settings
from app.inference.anthropic_provider import AnthropicProvider
from app.inference.bootstrap import build_model_router
from app.inference.freellmapi_provider import FreeLLMAPIProvider


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "development",
        "secret_key": "a" * 32,
        "creator_bootstrap_username": "creator",
        "creator_bootstrap_password": "b" * 32,
        "database_url": "postgresql+asyncpg://creation:secret@postgres/db",
        "redis_url": "redis://redis:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def _configure_freellmapi_and_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto:default")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4")


def test_chain_is_primary_followed_by_declared_fallbacks() -> None:
    configured = _settings(llm_provider="freellmapi", llm_fallback_providers="anthropic, openai")
    assert configured.inference_provider_chain == ["freellmapi", "anthropic", "openai"]


def test_chain_is_primary_only_without_fallbacks() -> None:
    assert _settings(llm_provider="freellmapi").inference_provider_chain == ["freellmapi"]


def test_fallbacks_reject_fake() -> None:
    with pytest.raises(ValidationError, match="must not contain fake"):
        _settings(llm_provider="freellmapi", llm_fallback_providers="fake")


def test_fallbacks_reject_unsupported_provider() -> None:
    with pytest.raises(ValidationError, match="supported providers"):
        _settings(llm_provider="freellmapi", llm_fallback_providers="gemini")


def test_fallbacks_reject_repeating_the_primary_provider() -> None:
    with pytest.raises(ValidationError, match="must not repeat LLM_PROVIDER"):
        _settings(llm_provider="freellmapi", llm_fallback_providers="freellmapi")


def test_fallbacks_reject_duplicates() -> None:
    with pytest.raises(ValidationError, match="must not repeat a provider"):
        _settings(llm_provider="freellmapi", llm_fallback_providers="anthropic,anthropic")


def test_build_model_router_registers_the_whole_chain(monkeypatch) -> None:
    _configure_freellmapi_and_anthropic(monkeypatch)
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")

    router = build_model_router()

    assert router.registry.names() == ("freellmapi", "anthropic")
    assert isinstance(router.registry.get("freellmapi"), FreeLLMAPIProvider)
    assert isinstance(router.registry.get("anthropic"), AnthropicProvider)
    anthropic_profile = router.registry.get_default_model_profile("anthropic")
    assert anthropic_profile is not None
    assert anthropic_profile.model == "claude-sonnet-4"


def test_build_model_router_fails_closed_when_a_fallback_is_unconfigured(monkeypatch) -> None:
    _configure_freellmapi_and_anthropic(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is required"):
        build_model_router()
