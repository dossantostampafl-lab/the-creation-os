from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.inference.contracts import InferenceRequest, InferenceTimeoutError
from app.voice_session.inference import StreamChunk, stream_with_fallback


class StubProvider:
    def __init__(self, name: str, events: list[str | Exception]) -> None:
        self.name = name
        self.events = events
        self.calls = 0

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self.calls += 1
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


def request() -> InferenceRequest:
    return InferenceRequest(messages=[{"role": "user", "content": "Olá"}])


@pytest.mark.asyncio
async def test_stream_uses_primary_without_touching_fallback():
    primary = StubProvider("freellmapi", ["Olá", " mundo"])
    fallback = StubProvider("anthropic", ["reserva"])

    chunks = [
        chunk
        async for chunk in stream_with_fallback(
            request(),
            primary=primary,
            fallback=fallback,
            first_token_timeout_seconds=0.2,
        )
    ]

    assert chunks == [
        StreamChunk(provider="freellmapi", text="Olá"),
        StreamChunk(provider="freellmapi", text=" mundo"),
    ]
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_stream_falls_back_when_primary_fails_before_first_token():
    primary = StubProvider(
        "freellmapi",
        [InferenceTimeoutError("freellmapi", "timeout")],
    )
    fallback = StubProvider("anthropic", ["reserva"])

    chunks = [
        chunk
        async for chunk in stream_with_fallback(
            request(),
            primary=primary,
            fallback=fallback,
            first_token_timeout_seconds=0.2,
        )
    ]

    assert chunks == [StreamChunk(provider="anthropic", text="reserva")]
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_stream_never_interleaves_fallback_after_primary_emits_text():
    primary = StubProvider(
        "freellmapi",
        ["parcial", InferenceTimeoutError("freellmapi", "timeout")],
    )
    fallback = StubProvider("anthropic", ["não deve aparecer"])

    received: list[StreamChunk] = []
    with pytest.raises(InferenceTimeoutError):
        async for chunk in stream_with_fallback(
            request(),
            primary=primary,
            fallback=fallback,
            first_token_timeout_seconds=0.2,
        ):
            received.append(chunk)

    assert received == [StreamChunk(provider="freellmapi", text="parcial")]
    assert fallback.calls == 0
