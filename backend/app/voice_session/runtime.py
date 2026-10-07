from __future__ import annotations

import os
from dataclasses import dataclass

from loguru import logger

from app.config import settings
from app.inference.bootstrap import _register_provider
from app.inference.registry import ProviderRegistry
from app.voice_session.inference import StreamingProvider


@dataclass(frozen=True)
class VoiceInferenceRuntime:
    primary: StreamingProvider
    fallbacks: tuple[StreamingProvider, ...]
    primary_models: tuple[str, ...]


def _conversation_models() -> tuple[str, ...]:
    raw = os.getenv("DEUS_VOICE_CONVERSATION_MODELS", "")
    models = tuple(dict.fromkeys(model.strip() for model in raw.split(",") if model.strip()))
    if any(model.casefold() == "auto" for model in models):
        raise RuntimeError("DEUS_VOICE_CONVERSATION_MODELS must list explicit conversational models")
    if len(models) > 4:
        raise RuntimeError("DEUS_VOICE_CONVERSATION_MODELS supports at most four models")
    return models


def build_voice_inference_runtime() -> VoiceInferenceRuntime:
    primary_name = settings.deus_voice_primary_provider
    registry = ProviderRegistry()
    _register_provider(registry, primary_name)
    fallbacks: list[StreamingProvider] = []
    # SIWC plan requests must stop on ChatGPT errors rather than silently changing
    # provider/billing path, unless the operator enabled the disclosed fallback: voice then
    # reports the provider that answered and why (provider_selected/fallback_reason telemetry).
    if primary_name == "chatgpt" and not settings.chatgpt_fallback_enabled:
        return VoiceInferenceRuntime(
            primary=registry.get(primary_name),
            fallbacks=(),
            primary_models=(),
        )
    for provider_name in settings.inference_provider_chain:
        if provider_name == primary_name:
            continue
        try:
            _register_provider(registry, provider_name)
        except (RuntimeError, ValueError) as exc:
            logger.bind(
                component="voice_inference",
                provider=provider_name,
                error_type=exc.__class__.__name__,
            ).warning("voice inference fallback skipped: {}", exc)
            continue
        fallbacks.append(registry.get(provider_name))

    return VoiceInferenceRuntime(
        primary=registry.get(primary_name),
        fallbacks=tuple(fallbacks),
        primary_models=_conversation_models() if primary_name == "freellmapi" else (),
    )


def build_primary_provider() -> StreamingProvider:
    """Compatibility shim for callers/tests that only need the configured primary."""
    return build_voice_inference_runtime().primary
