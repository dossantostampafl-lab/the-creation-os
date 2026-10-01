from __future__ import annotations

from app.config import settings
from app.inference.bootstrap import _register_provider
from app.inference.registry import ProviderRegistry
from app.voice_session.inference import StreamingProvider


def build_primary_provider() -> StreamingProvider:
    if settings.deus_voice_primary_provider != "freellmapi":
        raise RuntimeError("DEUS_VOICE_PRIMARY_PROVIDER must be freellmapi")
    registry = ProviderRegistry()
    _register_provider(registry, "freellmapi")
    return registry.get("freellmapi")
