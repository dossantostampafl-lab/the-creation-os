from __future__ import annotations

from app.config import settings
from app.inference.contracts import InferenceRequest, InferenceResponse, ProviderHealth
from app.voice_session import runtime


class StubProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.default_model = name + "-model"

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(provider=self.name, model=self.default_model, content="ok")

    async def stream(self, request: InferenceRequest):
        if False:
            yield ""
        return


def test_chatgpt_voice_runtime_does_not_register_a_billing_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chatgpt_fallback_enabled", False)
    monkeypatch.setattr(settings, "deus_voice_primary_provider", "chatgpt")
    monkeypatch.setattr(settings, "llm_provider", "chatgpt")
    monkeypatch.setattr(settings, "llm_fallback_providers", "freellmapi")
    registered: list[str] = []

    def fake_register(registry, provider_name: str) -> None:
        registered.append(provider_name)
        registry.register(StubProvider(provider_name))

    monkeypatch.setattr(runtime, "_register_provider", fake_register)

    built = runtime.build_voice_inference_runtime()

    assert built.primary.name == "chatgpt"
    assert built.fallbacks == ()
    assert registered == ["chatgpt"]


def test_chatgpt_voice_runtime_uses_the_disclosed_reserve_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "chatgpt_fallback_enabled", True)
    monkeypatch.setattr(settings, "deus_voice_primary_provider", "chatgpt")
    monkeypatch.setattr(settings, "llm_provider", "chatgpt")
    monkeypatch.setattr(settings, "llm_fallback_providers", "freellmapi")
    registered: list[str] = []

    def fake_register(registry, provider_name: str) -> None:
        registered.append(provider_name)
        registry.register(StubProvider(provider_name))

    monkeypatch.setattr(runtime, "_register_provider", fake_register)

    built = runtime.build_voice_inference_runtime()

    assert built.primary.name == "chatgpt"
    assert [item.name for item in built.fallbacks] == ["freellmapi"]
    assert registered == ["chatgpt", "freellmapi"]
