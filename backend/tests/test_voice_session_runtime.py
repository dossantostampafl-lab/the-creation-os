from __future__ import annotations

import importlib
from collections.abc import AsyncIterator

import pytest

from app.config import settings
from app.inference.contracts import InferenceRequest


class StubProvider:
    name = "anthropic"

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        yield "ok"


def test_voice_runtime_defaults_match_the_approved_contract():
    assert settings.deus_voice_primary_provider == "freellmapi"
    assert settings.deus_voice_fallback_provider == "klaus"
    assert settings.deus_voice_first_token_timeout_ms == 2500


def test_klaus_requires_an_explicit_concrete_provider(monkeypatch):
    runtime = importlib.import_module("app.voice_session.runtime")
    monkeypatch.setattr(settings, "klaus_provider", "")

    with pytest.raises(RuntimeError, match="KLAUS_PROVIDER"):
        runtime.build_klaus_provider()


@pytest.mark.asyncio
async def test_klaus_alias_keeps_the_logical_provider_name():
    runtime = importlib.import_module("app.voice_session.runtime")
    aliased = runtime.AliasedStreamingProvider("klaus", StubProvider())

    chunks = [
        item
        async for item in aliased.stream(
            InferenceRequest(messages=[{"role": "user", "content": "Olá"}])
        )
    ]

    assert aliased.name == "klaus"
    assert chunks == ["ok"]
