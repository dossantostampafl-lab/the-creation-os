from __future__ import annotations

from collections.abc import AsyncIterator

from app.config import settings
from app.inference.bootstrap import _register_provider
from app.inference.contracts import InferenceRequest
from app.inference.registry import ProviderRegistry
from app.voice_session.inference import StreamingProvider


class AliasedStreamingProvider:
    def __init__(self, name: str, provider: StreamingProvider) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("provider alias is required")
        self.name = normalized
        self._provider = provider

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        async for chunk in self._provider.stream(request):
            yield chunk


def _build_concrete_provider(name: str) -> StreamingProvider:
    normalized = name.strip().lower()
    if not normalized:
        raise RuntimeError("concrete provider is required")
    registry = ProviderRegistry()
    _register_provider(registry, normalized)
    return registry.get(normalized)


def build_primary_provider() -> StreamingProvider:
    if settings.deus_voice_primary_provider != "freellmapi":
        raise RuntimeError("DEUS_VOICE_PRIMARY_PROVIDER must be freellmapi")
    return _build_concrete_provider("freellmapi")


def build_klaus_provider() -> StreamingProvider:
    concrete = settings.klaus_provider.strip().lower()
    if not concrete:
        raise RuntimeError(
            "KLAUS_PROVIDER must explicitly map the logical klaus fallback "
            "to a configured concrete streaming provider"
        )
    if concrete == "freellmapi":
        raise RuntimeError("KLAUS_PROVIDER must not duplicate the FreeLLM primary")
    return AliasedStreamingProvider("klaus", _build_concrete_provider(concrete))
