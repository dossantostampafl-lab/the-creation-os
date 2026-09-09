from __future__ import annotations

from pydantic.v1 import SecretStr

from app.config import settings
from app.inference.bootstrap import build_model_router
from app.inference.freellmapi_provider import FreeLLMAPIProvider


def test_build_model_router_registers_freellmapi_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_model", "auto:default")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("gateway-secret"))
    monkeypatch.setattr(settings, "freellmapi_base_url", "http://freellmapi:3001/v1")
    monkeypatch.setattr(settings, "freellmapi_timeout_seconds", 12.5)

    router = build_model_router()
    provider = router._registry.get("freellmapi")

    assert isinstance(provider, FreeLLMAPIProvider)
    assert provider._base_url == "http://freellmapi:3001/v1"
    assert provider._timeout_seconds == 12.5


def test_build_model_router_requires_freellmapi_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_model", "auto:default")
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "freellmapi_base_url", "http://freellmapi:3001/v1")
    monkeypatch.setattr(settings, "freellmapi_timeout_seconds", 60.0)

    try:
        build_model_router()
    except RuntimeError as exc:
        assert str(exc) == "LLM_API_KEY is required when LLM_PROVIDER=freellmapi"
    else:
        raise AssertionError("expected missing FreeLLMAPI key to fail closed")
