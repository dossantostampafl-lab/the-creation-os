from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from app.config import settings
from app.inference.anthropic_config import load_anthropic_config
from app.inference.anthropic_provider import REFUSAL_FALLBACK_BETA, AnthropicProvider
from app.inference.bootstrap import build_model_router
from app.inference.contracts import (
    InferenceAuthenticationError,
    InferenceRateLimitError,
    InferenceRequest,
    InferenceUpstreamResponseError,
    ModelRequirements,
)


class FakeStream:
    def __init__(self, message: Any, chunks: list[str]) -> None:
        self._message = message
        self.text_stream = self._text(chunks)

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get_final_message(self) -> Any:
        return self._message

    @staticmethod
    async def _text(chunks: list[str]) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk


class FakeMessages:
    def __init__(self, outcome: Any, chunks: list[str]) -> None:
        self.outcome = outcome
        self.chunks = chunks
        self.calls: list[dict[str, Any]] = []

    def stream(self, **params: Any) -> FakeStream:
        self.calls.append(params)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return FakeStream(self.outcome, self.chunks)


class FakeModels:
    def __init__(self, outcome: Exception | None = None) -> None:
        self.outcome = outcome

    async def retrieve(self, model: str) -> Any:
        if self.outcome is not None:
            raise self.outcome
        return SimpleNamespace(id=model)


def fake_client(outcome: Any = None, chunks: list[str] | None = None, models_error: Exception | None = None) -> Any:
    messages = FakeMessages(outcome, chunks or [])
    return SimpleNamespace(beta=SimpleNamespace(messages=messages), models=FakeModels(models_error))


def claude_message(text: str, stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        model="claude-opus-5",
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=12, output_tokens=5),
    )


def status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx.Response(status, request=request), body=None)


def deus_request(**requirements: Any) -> InferenceRequest:
    return InferenceRequest(
        messages=[
            {"role": "system", "content": "You are DEUS."},
            {"role": "user", "content": "Status?"},
            {"role": "assistant", "content": "Operational."},
            {"role": "user", "content": "And the universes?"},
        ],
        requirements=ModelRequirements(**requirements),
    )


async def test_generate_moves_system_prompt_and_returns_text() -> None:
    client = fake_client(claude_message("All universes are breathing."))
    provider = AnthropicProvider(api_key="", default_model="claude-opus-5", client=client)

    response = await provider.generate(deus_request())

    params = client.beta.messages.calls[0]
    assert params["system"] == "You are DEUS."
    assert [m["role"] for m in params["messages"]] == ["user", "assistant", "user"]
    assert params["model"] == "claude-opus-5"
    assert params["max_tokens"] == 16000
    assert "fallbacks" not in params
    assert response.provider == "anthropic"
    assert response.content == "All universes are breathing."
    assert response.finish_reason == "end_turn"
    assert response.usage == {"input_tokens": 12, "output_tokens": 5}


async def test_generate_opts_into_refusal_fallback_and_effort() -> None:
    client = fake_client(claude_message("ok"))
    provider = AnthropicProvider(api_key="", default_model="claude-opus-5", effort="medium", refusal_fallback=True, client=client)

    await provider.generate(deus_request(max_output_tokens=512))

    params = client.beta.messages.calls[0]
    assert params["betas"] == [REFUSAL_FALLBACK_BETA]
    assert params["fallbacks"] == "default"
    assert params["output_config"] == {"effort": "medium"}
    assert params["max_tokens"] == 512


async def test_generate_rejects_refusals() -> None:
    provider = AnthropicProvider(api_key="", default_model="claude-opus-5", client=fake_client(claude_message("", "refusal")))

    with pytest.raises(InferenceUpstreamResponseError):
        await provider.generate(deus_request())


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (status_error(anthropic.AuthenticationError, 401), InferenceAuthenticationError),
        (status_error(anthropic.RateLimitError, 429), InferenceRateLimitError),
        (status_error(anthropic.InternalServerError, 500), InferenceUpstreamResponseError),
    ],
)
async def test_generate_translates_sdk_errors(error: Exception, expected: type[Exception]) -> None:
    provider = AnthropicProvider(api_key="", default_model="claude-opus-5", client=fake_client(error))

    with pytest.raises(expected):
        await provider.generate(deus_request())


async def test_stream_yields_text_chunks() -> None:
    provider = AnthropicProvider(api_key="", default_model="claude-opus-5", client=fake_client(claude_message(""), ["All ", "breathing."]))

    chunks = [chunk async for chunk in provider.stream(deus_request())]

    assert chunks == ["All ", "breathing."]


async def test_health_reports_authentication_failure() -> None:
    client = fake_client(models_error=status_error(anthropic.AuthenticationError, 401))
    provider = AnthropicProvider(api_key="", default_model="claude-opus-5", client=client)

    health = await provider.health()

    assert health.available is False
    assert health.detail == "authentication_failed"


def test_config_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "llm_model", "claude-opus-5")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        load_anthropic_config()


def test_config_requires_a_real_model(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(settings, "llm_model", "fake")

    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        load_anthropic_config()


def test_refusal_fallback_only_applies_to_capable_models(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_REFUSAL_FALLBACK", raising=False)
    monkeypatch.setattr(settings, "llm_model", "claude-sonnet-5")
    assert load_anthropic_config().refusal_fallback is False

    monkeypatch.setattr(settings, "llm_model", "claude-opus-5")
    assert load_anthropic_config().refusal_fallback is True

    monkeypatch.setenv("ANTHROPIC_REFUSAL_FALLBACK", "off")
    assert load_anthropic_config().refusal_fallback is False


def test_build_model_router_registers_anthropic_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-opus-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    router = build_model_router()
    provider = router.registry.get("anthropic")
    profile = router.registry.get_default_model_profile("anthropic")

    assert isinstance(provider, AnthropicProvider)
    assert profile is not None
    assert profile.model == "claude-opus-5"
    assert profile.capabilities == frozenset({"text", "streaming"})
