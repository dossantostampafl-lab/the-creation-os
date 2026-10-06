import pytest

from app.config import settings
from app.voice_session.runtime import build_voice_inference_runtime


def _configure_free_primary(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "")


def test_voice_runtime_uses_free_primary_and_existing_timeout():
    assert settings.deus_voice_primary_provider == "freellmapi"
    assert settings.deus_voice_first_token_timeout_ms == 2500


def test_empty_conversation_pool_preserves_legacy_primary(monkeypatch):
    _configure_free_primary(monkeypatch)
    monkeypatch.setattr(settings, "llm_fallback_providers", "")
    monkeypatch.delenv("DEUS_VOICE_CONVERSATION_MODELS", raising=False)

    runtime = build_voice_inference_runtime()

    assert runtime.primary.name == "freellmapi"
    assert runtime.primary_models == ()
    assert runtime.fallbacks == ()


def test_explicit_conversation_pool_is_ordered_and_deduplicated(monkeypatch):
    _configure_free_primary(monkeypatch)
    monkeypatch.setattr(settings, "llm_fallback_providers", "")
    monkeypatch.setenv(
        "DEUS_VOICE_CONVERSATION_MODELS",
        "model-fast, model-quality, model-fast",
    )

    runtime = build_voice_inference_runtime()

    assert runtime.primary_models == ("model-fast", "model-quality")


def test_auto_is_rejected_inside_curated_voice_pool(monkeypatch):
    _configure_free_primary(monkeypatch)
    monkeypatch.setattr(settings, "llm_fallback_providers", "")
    monkeypatch.setenv("DEUS_VOICE_CONVERSATION_MODELS", "model-fast,auto")

    with pytest.raises(RuntimeError, match="explicit conversational models"):
        build_voice_inference_runtime()


def test_voice_runtime_reuses_configured_anthropic_reserve(monkeypatch):
    _configure_free_primary(monkeypatch)
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-model")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setenv("DEUS_VOICE_CONVERSATION_MODELS", "model-a,model-b")

    runtime = build_voice_inference_runtime()

    assert runtime.primary.name == "freellmapi"
    assert runtime.primary_models == ("model-a", "model-b")
    assert [provider.name for provider in runtime.fallbacks] == ["anthropic"]


def test_voice_keeps_anthropic_when_chat_uses_it_as_primary(monkeypatch):
    _configure_free_primary(monkeypatch)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_providers", "freellmapi")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-model")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setenv("DEUS_VOICE_CONVERSATION_MODELS", "model-a")

    runtime = build_voice_inference_runtime()

    assert runtime.primary.name == "freellmapi"
    assert [provider.name for provider in runtime.fallbacks] == ["anthropic"]
