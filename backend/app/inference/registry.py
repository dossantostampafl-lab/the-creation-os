from __future__ import annotations

from typing import Any

from app.inference.contracts import ProviderModelProfile, ProviderUnavailable


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}
        self._model_profiles: dict[tuple[str, str], ProviderModelProfile] = {}
        self._default_models: dict[str, str] = {}

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

    def register_model_profile(self, profile: ProviderModelProfile) -> None:
        if profile.provider not in self._providers:
            raise ValueError(f"provider not registered: {profile.provider}")
        key = (profile.provider, profile.model)
        if key in self._model_profiles:
            raise ValueError(
                f"profile already registered: {profile.provider}/{profile.model}"
            )
        if profile.is_default and profile.provider in self._default_models:
            raise ValueError(
                f"default model already registered for provider: {profile.provider}"
            )
        self._model_profiles[key] = profile
        if profile.is_default:
            self._default_models[profile.provider] = profile.model

    def get_model_profile(self, provider: str, model: str) -> ProviderModelProfile | None:
        return self._model_profiles.get((provider, model))

    def get_default_model_profile(self, provider: str) -> ProviderModelProfile | None:
        model = self._default_models.get(provider)
        if model is None:
            return None
        return self._model_profiles.get((provider, model))

    def model_profiles(self, provider: str) -> tuple[ProviderModelProfile, ...]:
        profiles = [
            profile
            for (provider_name, _), profile in self._model_profiles.items()
            if provider_name == provider
        ]
        return tuple(sorted(profiles, key=lambda profile: profile.model))

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)
