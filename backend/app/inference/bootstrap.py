from __future__ import annotations

from app.config import settings
from app.inference.freellmapi_provider import FreeLLMAPIProvider
from app.inference.openai_provider import OpenAIResponsesProvider
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter


def build_model_router() -> ModelRouter:
    registry = ProviderRegistry()
    provider = settings.llm_provider.strip().lower()
    if provider == "openai":
        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
            raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        registry.register(
            OpenAIResponsesProvider(
                api_key=settings.llm_api_key.get_secret_value(),
                default_model=settings.llm_model,
            )
        )
    elif provider == "freellmapi":
        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
            raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER=freellmapi")
        registry.register(
            FreeLLMAPIProvider(
                api_key=settings.llm_api_key.get_secret_value(),
                default_model=settings.llm_model,
                base_url=settings.freellmapi_base_url,
                timeout_seconds=settings.freellmapi_timeout_seconds,
            )
        )
    elif provider == "fake":
        raise RuntimeError("fake inference provider is test-only and cannot power the operational runtime")
    else:
        raise RuntimeError(f"unsupported LLM_PROVIDER: {provider or '<empty>'}")
    return ModelRouter(registry)
