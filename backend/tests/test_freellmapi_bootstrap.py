from __future__ import annotations

from pydantic.v1 import SecretStr

from app.config import settings
from app.inference.bootstrap import build_model_router
from app.inference.freellmapi_provider import FreeLLMAPIProvider


def test_build_model_router_registers_freellmapi_from_dedicated_environment(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_model", "must-not-be-used")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("must-not-be-used"))
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto:default")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("FREELLMAPI_TIMEOUT_SECONDS", "12.5")

    router = build_model_router()
    provider = router.registry.get("freellmapi")

    assert isinstance(provider, FreeLLMAPIProvider)
    assert provider._base_url == "http://freellmapi:3001/v1"
    assert provider._default_model == "auto:default"
    assert provider._timeout_seconds == 12.5


def test_build_model_router_requires_freellmapi_api_key_even_when_llm_key_exists(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("openai-key-must-not-be-used"))
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto:default")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")

    try:
        build_model_router()
    except RuntimeError as exc:
        assert str(exc) == "FREELLMAPI_API_KEY is required when LLM_PROVIDER=freellmapi"
    else:
        raise AssertionError("expected missing FreeLLMAPI key to fail closed")


def test_build_model_router_requires_explicit_freellmapi_base_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto:default")
    monkeypatch.delenv("FREELLMAPI_BASE_URL", raising=False)

    try:
        build_model_router()
    except RuntimeError as exc:
        assert str(exc) == "FREELLMAPI_BASE_URL is required when LLM_PROVIDER=freellmapi"
    else:
        raise AssertionError("expected missing FreeLLMAPI base URL to fail closed")


def test_build_model_router_requires_freellmapi_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.delenv("FREELLMAPI_MODEL", raising=False)
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")

    try:
        build_model_router()
    except RuntimeError as exc:
        assert str(exc) == "FREELLMAPI_MODEL is required when LLM_PROVIDER=freellmapi"
    else:
        raise AssertionError("expected missing FreeLLMAPI model to fail closed")


def test_build_model_router_rejects_invalid_freellmapi_timeout(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "gateway-secret")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto:default")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
    monkeypatch.setenv("FREELLMAPI_TIMEOUT_SECONDS", "0")

    try:
        build_model_router()
    except RuntimeError as exc:
        assert str(exc) == "FREELLMAPI_TIMEOUT_SECONDS must be greater than zero"
    else:
        raise AssertionError("expected invalid FreeLLMAPI timeout to fail closed")
