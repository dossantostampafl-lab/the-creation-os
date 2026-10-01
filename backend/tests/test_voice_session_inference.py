from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.inference.contracts import InferenceRequest, InferenceTimeoutError
from app.voice_session.inference import StreamChunk, stream_response


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


class SlowProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        await asyncio.sleep(1)
        yield "too late"


def request() -> InferenceRequest:
    return InferenceRequest(messages=[{"role": "user", "content": "Olá"}])


@pytest.mark.asyncio
async def test_stream_uses_primary_from_free_primary():
    primary = StubProvider("freellmapi", ["Olá", " mundo"])

    chunks = [
        chunk
        async for chunk in stream_response(
            request(),
            primary=primary,
            first_token_timeout_seconds=0.2,
        )
    ]

    assert chunks == [
        StreamChunk(provider="freellmapi", text="Olá"),
        StreamChunk(provider="freellmapi", text=" mundo"),
    ]
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_stream_propagates_failure_after_primary_emits_text():
    primary = StubProvider(
        "freellmapi",
        ["parcial", InferenceTimeoutError("freellmapi", "timeout")],
    )

    received: list[StreamChunk] = []
    with pytest.raises(InferenceTimeoutError):
        async for chunk in stream_response(
            request(),
            primary=primary,
            first_token_timeout_seconds=0.2,
        ):
            received.append(chunk)

    assert received == [StreamChunk(provider="freellmapi", text="parcial")]
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_primary_first_token_is_bounded_without_another_provider():
    with pytest.raises(InferenceTimeoutError) as error:
        _ = [chunk async for chunk in stream_response(
            request(), primary=SlowProvider("freellmapi"), first_token_timeout_seconds=0.01,
        )]
    assert error.value.provider == "freellmapi"


@pytest.mark.asyncio
async def test_transient_first_token_timeout_retries_the_same_free_provider_once():
    class RecoveringProvider:
        name = "freellmapi"
        calls = 0

        async def stream(self, request):
            self.calls += 1
            if self.calls == 1:
                raise InferenceTimeoutError(self.name, "temporary timeout")
            yield "Quatro."

    primary = RecoveringProvider()
    chunks = [chunk async for chunk in stream_response(request(), primary=primary)]
    assert chunks == [StreamChunk(provider="freellmapi", text="Quatro.")]
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_first_token_deadline_retries_once_and_closes_the_cancelled_stream():
    class RecoveringProvider:
        name = "freellmapi"
        calls = 0
        closed = False

        async def stream(self, request):
            self.calls += 1
            if self.calls == 1:
                try:
                    await asyncio.Event().wait()
                finally:
                    self.closed = True
            yield "Quatro."

    primary = RecoveringProvider()
    chunks = [chunk async for chunk in stream_response(
        request(), primary=primary, first_token_timeout_seconds=0.01,
    )]
    assert chunks == [StreamChunk(provider="freellmapi", text="Quatro.")]
    assert primary.calls == 2
    assert primary.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("error_name", ["InferenceAuthenticationError", "InferenceRateLimitError"])
async def test_authentication_and_rate_limits_are_not_retried(error_name):
    from app.inference import contracts

    primary = StubProvider("freellmapi", [getattr(contracts, error_name)("freellmapi", "unavailable")])
    with pytest.raises(InferenceTimeoutError):
        _ = [chunk async for chunk in stream_response(request(), primary=primary)]
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_persistent_first_token_timeout_stops_after_two_attempts():
    primary = StubProvider("freellmapi", [InferenceTimeoutError("freellmapi", "unavailable")])
    with pytest.raises(InferenceTimeoutError):
        _ = [chunk async for chunk in stream_response(request(), primary=primary)]
    assert primary.calls == 2
