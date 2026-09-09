from __future__ import annotations

from pydantic.v1 import SecretStr

from app.config import settings
from app.inference.bootstrap import build_model_router


def test_openai_bootstrap_registers_conservative_default_profile(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "configured-openai-model")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test-openai-key"))

    router = build_model_router()
    profile = router.registry.get_default_model_profile("openai")

    assert profile is not None
    assert profile.provider == "openai"
    assert profile.model == "configured-openai-model"
    assert profile.capabilities == frozenset({"text", "streaming"})
    assert profile.is_default is True


def test_freellmapi_bootstrap_registers_conservative_default_profile(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.setenv("FREELLMAPI_MODEL", "gateway-model")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("FREELLMAPI_TIMEOUT_SECONDS", "60")

    router = build_model_router()
    profile = router.registry.get_default_model_profile("freellmapi")

    assert profile is not None
    assert profile.provider == "freellmapi"
    assert profile.model == "gateway-model"
    assert profile.capabilities == frozenset({"text", "streaming"})
    assert profile.is_default is True
    assert "tools" not in profile.capabilities
    assert "vision" not in profile.capabilities
