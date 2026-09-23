from __future__ import annotations

from app.cache.bootstrap import build_cache_orchestrator
from app.cache.routing import CachingModelRouter
from app.config import settings
from app.inference.anthropic_config import load_anthropic_config
from app.inference.anthropic_provider import AnthropicProvider
from app.inference.contracts import ProviderModelProfile
from app.inference.freellmapi_config import load_freellmapi_config, load_freellmapi_model
from app.inference.freellmapi_provider import FreeLLMAPIProvider
from app.inference.health import ProviderCircuitBreaker, ProviderRateLimitCooldown
from app.inference.openai_compatible_config import load_openai_compatible_config
from app.inference.openai_compatible_provider import OpenAICompatibleProvider
from app.inference.openai_provider import OpenAIResponsesProvider
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter

# Routers are built per request, but a provider's health is a fact about the process's world:
# once FreeLLMAPI's circuit opens, every request should go straight to the fallback until it recovers.
_CIRCUIT_BREAKER = ProviderCircuitBreaker()
_RATE_LIMIT_COOLDOWN = ProviderRateLimitCooldown()


def resolve_configured_model(router: ModelRouter) -> str:
    """Model the configured provider actually serves, which may differ from LLM_MODEL."""
    profile = router.registry.get_default_model_profile(settings.llm_provider.strip().lower())
    return profile.model if profile is not None else settings.llm_model


def _register_provider(registry: ProviderRegistry, provider: str) -> None:
    if provider == "openai":
        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
            raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        registry.register(
            OpenAIResponsesProvider(
                api_key=settings.llm_api_key.get_secret_value(),
                default_model=settings.llm_model,
            )
        )
        registry.register_model_profile(
            ProviderModelProfile(
                provider="openai",
                model=settings.llm_model,
                capabilities=frozenset({"text", "streaming"}),
                is_default=True,
            )
        )
    elif provider == "anthropic":
        anthropic_config = load_anthropic_config()
        registry.register(
            AnthropicProvider(
                api_key=anthropic_config.api_key.get_secret_value(),
                default_model=anthropic_config.model,
                base_url=anthropic_config.base_url,
                timeout_seconds=anthropic_config.timeout_seconds,
                max_output_tokens=anthropic_config.max_output_tokens,
            )
        )
        registry.register_model_profile(
            ProviderModelProfile(
                provider="anthropic",
                model=anthropic_config.model,
                capabilities=frozenset({"text", "streaming"}),
                is_default=True,
            )
        )
    elif provider == "freellmapi":
        gateway_config = load_freellmapi_config()
        model = load_freellmapi_model()
        registry.register(
            FreeLLMAPIProvider(
                api_key=gateway_config.api_key.get_secret_value(),
                default_model=model,
                base_url=gateway_config.base_url,
                timeout_seconds=gateway_config.timeout_seconds,
            )
        )
        registry.register_model_profile(
            ProviderModelProfile(
                provider="freellmapi",
                model=model,
                capabilities=frozenset({"text", "streaming"}),
                is_default=True,
            )
        )
    elif provider == "openai_compatible":
        compatible_config = load_openai_compatible_config()
        registry.register(
            OpenAICompatibleProvider(
                name="openai_compatible",
                api_key=(
                    compatible_config.api_key.get_secret_value()
                    if compatible_config.api_key is not None
                    else None
                ),
                default_model=compatible_config.model,
                base_url=compatible_config.base_url,
                timeout_seconds=compatible_config.timeout_seconds,
            )
        )
        registry.register_model_profile(
            ProviderModelProfile(
                provider="openai_compatible",
                model=compatible_config.model,
                capabilities=frozenset({"text", "streaming"}),
                is_default=True,
            )
        )
    elif provider == "fake":
        raise RuntimeError("fake inference provider is test-only and cannot power the operational runtime")
    else:
        raise RuntimeError(f"unsupported LLM_PROVIDER: {provider or '<empty>'}")


def build_model_router() -> ModelRouter:
    """Every request is served by the configured provider; the chain's fallbacks only when it fails."""
    registry = ProviderRegistry()
    chain = settings.inference_provider_chain
    for provider in chain:
        _register_provider(registry, provider)
    return CachingModelRouter(
        registry,
        cache=build_cache_orchestrator(),
        fallback_providers=chain[1:],
        circuit_breaker=_CIRCUIT_BREAKER,
        rate_limit_cooldown=_RATE_LIMIT_COOLDOWN,
    )
