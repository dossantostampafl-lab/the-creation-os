from __future__ import annotations

import pytest

from app.config import settings
from app.inference.anthropic_config import load_anthropic_config
from app.inference.anthropic_provider import AnthropicProvider
from app.inference.bootstrap import build_model_router
from app.inference.contracts import CostTier


@pytest.fixture(autouse=True)
def anthropic_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-model")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ANTHROPIC_MAX_OUTPUT_TOKENS", raising=False)
    return monkeypatch


def test_config_defaults_to_the_public_claude_endpoint() -> None:
    config = load_anthropic_config()

    assert config.base_url == "https://api.anthropic.com/v1"
    assert config.model == "claude-model"
    assert config.api_key.get_secret_value() == "anthropic-secret"
    assert config.timeout_seconds == 60.0
    assert config.max_output_tokens == 4096


def test_config_reads_overrides(anthropic_env) -> None:
    anthropic_env.setenv("ANTHROPIC_BASE_URL", "https://gateway.invalid/v1")
    anthropic_env.setenv("ANTHROPIC_TIMEOUT_SECONDS", "12.5")
    anthropic_env.setenv("ANTHROPIC_MAX_OUTPUT_TOKENS", "1024")

    config = load_anthropic_config()

    assert config.base_url == "https://gateway.invalid/v1"
    assert config.timeout_seconds == 12.5
    assert config.max_output_tokens == 1024


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("ANTHROPIC_API_KEY", "", "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"),
        ("ANTHROPIC_MODEL", "", "ANTHROPIC_MODEL is required when LLM_PROVIDER=anthropic"),
        ("ANTHROPIC_BASE_URL", "file:///tmp/model", "ANTHROPIC_BASE_URL must use http or https"),
        ("ANTHROPIC_TIMEOUT_SECONDS", "0", "ANTHROPIC_TIMEOUT_SECONDS must be greater than zero"),
        ("ANTHROPIC_TIMEOUT_SECONDS", "fast", "ANTHROPIC_TIMEOUT_SECONDS must be numeric"),
        ("ANTHROPIC_MAX_OUTPUT_TOKENS", "0", "ANTHROPIC_MAX_OUTPUT_TOKENS must be greater than zero"),
        ("ANTHROPIC_MAX_OUTPUT_TOKENS", "many", "ANTHROPIC_MAX_OUTPUT_TOKENS must be an integer"),
    ],
)
def test_config_fails_closed_on_invalid_settings(anthropic_env, variable: str, value: str, message: str) -> None:
    anthropic_env.setenv(variable, value)

    with pytest.raises(RuntimeError, match=message):
        load_anthropic_config()


def test_build_model_router_registers_anthropic_provider(anthropic_env) -> None:
    anthropic_env.setattr(settings, "llm_provider", "anthropic")

    router = build_model_router()
    provider = router.registry.get("anthropic")
    profile = router.registry.get_default_model_profile("anthropic")

    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"
    assert profile is not None
    assert profile.model == "claude-model"
    assert profile.capabilities == frozenset({"text", "streaming"})
    assert profile.cost_tier is CostTier.UNKNOWN
