from __future__ import annotations

from app.inference.openai_compatible_config import load_openai_compatible_config

from app.config import settings
from app.inference.bootstrap import build_model_router
from app.inference.contracts import CostTier
from app.inference.openai_compatible_provider import OpenAICompatibleProvider


def test_openai_compatible_config_accepts_optional_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "local-model")
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "12.5")

    config = load_openai_compatible_config()

    assert config.base_url == "http://ollama:11434/v1"
    assert config.model == "local-model"
    assert config.api_key is None
    assert config.timeout_seconds == 12.5


def test_build_model_router_registers_openai_compatible_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://gateway:8000/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "model-a")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "gateway-secret")
    monkeypatch.setenv("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "9")

    router = build_model_router()
    provider = router.registry.get("openai_compatible")
    profile = router.registry.get_default_model_profile("openai_compatible")

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "openai_compatible"
    assert provider._base_url == "http://gateway:8000/v1"
    assert provider._default_model == "model-a"
    assert provider._timeout_seconds == 9.0
    assert profile is not None
    assert profile.model == "model-a"
    assert profile.capabilities == frozenset({"text", "streaming"})
    assert profile.cost_tier is CostTier.UNKNOWN


def test_openai_compatible_config_requires_explicit_url(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "model-a")

    try:
        load_openai_compatible_config()
    except RuntimeError as exc:
        assert str(exc) == "OPENAI_COMPATIBLE_BASE_URL is required when LLM_PROVIDER=openai_compatible"
    else:
        raise AssertionError("expected missing OpenAI-compatible base URL to fail closed")


def test_openai_compatible_config_requires_explicit_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://gateway:8000/v1")
    monkeypatch.delenv("OPENAI_COMPATIBLE_MODEL", raising=False)

    try:
        load_openai_compatible_config()
    except RuntimeError as exc:
        assert str(exc) == "OPENAI_COMPATIBLE_MODEL is required when LLM_PROVIDER=openai_compatible"
    else:
        raise AssertionError("expected missing OpenAI-compatible model to fail closed")


def test_openai_compatible_config_rejects_invalid_url_and_timeout(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "file:///tmp/model")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "model-a")
    monkeypatch.setenv("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "0")

    try:
        load_openai_compatible_config()
    except RuntimeError as exc:
        assert str(exc) == "OPENAI_COMPATIBLE_BASE_URL must use http or https"
    else:
        raise AssertionError("expected invalid OpenAI-compatible URL to fail closed")

    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://gateway:8000/v1")
    try:
        load_openai_compatible_config()
    except RuntimeError as exc:
        assert str(exc) == "OPENAI_COMPATIBLE_TIMEOUT_SECONDS must be greater than zero"
    else:
        raise AssertionError("expected invalid OpenAI-compatible timeout to fail closed")
