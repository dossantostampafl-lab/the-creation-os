from __future__ import annotations

from typing import Any

from app.inference.contracts import ProviderUnavailable


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register(self, provider: Any) -> None:
        name = str(provider.name)
        if name in self._providers:
            raise ValueError(f"provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> Any:
        provider = self._providers.get(name)
        if provider is None:
            raise ProviderUnavailable(name, f"provider not registered: {name}")
        return provider

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)
