from app.autonomy.competition import InferenceThesisGenerator
from app.config import settings
from app.models.entities import Agent


def test_opportunity_agent_follows_runtime_provider_after_switch(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")
    agent = Agent(capabilities_json={"inference_provider": "anthropic", "inference_routing": "configured"})
    assert InferenceThesisGenerator._requirements(agent) == ("freellmapi", ["anthropic"], None)


def test_explicit_model_pin_is_preserved(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    agent = Agent(capabilities_json={"inference_provider": "anthropic", "model": "pinned-model"})
    assert InferenceThesisGenerator._requirements(agent) == ("anthropic", [], "pinned-model")
