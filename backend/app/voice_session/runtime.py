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
    if settings.deus_voice_primary_provider != "freellmapi":
        raise RuntimeError("DEUS_VOICE_PRIMARY_PROVIDER must be freellmapi")

    registry = ProviderRegistry()
    _register_provider(registry, "freellmapi")
    fallbacks: list[StreamingProvider] = []
    for provider_name in settings.inference_provider_chain[1:]:
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
        primary=registry.get("freellmapi"),
        fallbacks=tuple(fallbacks),
        primary_models=_conversation_models(),
    )


def build_primary_provider() -> StreamingProvider:
    """Compatibility shim for callers/tests that only need the FreeLLM primary."""
    return build_voice_inference_runtime().primary
