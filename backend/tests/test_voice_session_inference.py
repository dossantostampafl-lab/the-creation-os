from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.inference.contracts import (
    InferenceRateLimitError,
    InferenceRequest,
    InferenceTimeoutError,
)
from app.voice_session.inference import StreamChunk, stream_response


class StubProvider:
    def __init__(
        self,
        name: str,
        events: list[str | Exception],
        *,
        default_model: str | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.calls = 0
        self.requests: list[InferenceRequest] = []
        self.default_model = default_model

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self.calls += 1
        self.requests.append(request)
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


class SlowProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self.calls += 1
        await asyncio.sleep(1)
        yield "too late"


class ModelAwareProvider:
    name = "freellmapi"

    def __init__(self, behavior: dict[str | None, list[str | Exception] | str]) -> None:
        self.behavior = behavior
        self.models: list[str | None] = []

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self.models.append(request.model)
        events = self.behavior[request.model]
        if events == "slow":
            await asyncio.sleep(1)
            yield "late"
            return
        assert isinstance(events, list)
        for event in events:
            if isinstance(event, Exception):
                raise event
            yield event


def request() -> InferenceRequest:
    return InferenceRequest(messages=[{"role": "user", "content": "Olá"}])


@pytest.mark.asyncio
async def test_chatgpt_timeout_is_not_retried_before_configured_reserve():
    primary = StubProvider("chatgpt", [InferenceTimeoutError("chatgpt", "timeout")])
    reserve = StubProvider("freellmapi", ["Reserva."])
    chunks = [chunk async for chunk in stream_response(request(), primary=primary, fallbacks=(reserve,))]
    assert chunks == [StreamChunk(provider="freellmapi", text="Reserva.")]
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_chatgpt_gets_its_own_first_token_budget_without_extending_reserve_budget():
    class DelayedProvider(StubProvider):
        async def stream(self, request):
            await asyncio.sleep(0.03)
            async for text in super().stream(request):
                yield text

    primary = DelayedProvider("chatgpt", ["Resposta."])
    options = dict(first_token_timeout_seconds=0.01, first_token_timeouts_by_provider={"chatgpt": 0.1})
    chunks = [chunk async for chunk in stream_response(request(), primary=primary, **options)]
    assert chunks == [StreamChunk(provider="chatgpt", text="Resposta.")]

    failed = StubProvider("chatgpt", [InferenceRateLimitError("chatgpt", "limited")])
    with pytest.raises(InferenceTimeoutError):
        _ = [chunk async for chunk in stream_response(
            request(), primary=failed, fallbacks=(DelayedProvider("freellmapi", ["Late"]),), **options,
        )]


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
async def test_stream_propagates_failure_after_primary_emits_text_without_fallback():
    primary = StubProvider(
        "freellmapi",
        ["parcial", InferenceTimeoutError("freellmapi", "timeout")],
    )
    fallback = StubProvider("anthropic", ["não deve aparecer"])

    received: list[StreamChunk] = []
    with pytest.raises(InferenceTimeoutError):
        async for chunk in stream_response(
            request(),
            primary=primary,
            fallbacks=(fallback,),
            first_token_timeout_seconds=0.2,
        ):
            received.append(chunk)

    assert received == [StreamChunk(provider="freellmapi", text="parcial")]
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_primary_first_token_is_bounded_without_another_provider():
    with pytest.raises(InferenceTimeoutError) as error:
        _ = [
            chunk
            async for chunk in stream_response(
                request(),
                primary=SlowProvider("freellmapi"),
                first_token_timeout_seconds=0.01,
            )
        ]
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
    chunks = [
        chunk
        async for chunk in stream_response(
            request(),
            primary=primary,
            first_token_timeout_seconds=0.01,
        )
    ]
    assert chunks == [StreamChunk(provider="freellmapi", text="Quatro.")]
    assert primary.calls == 2
    assert primary.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_name",
    ["InferenceAuthenticationError", "InferenceRateLimitError"],
)
async def test_authentication_and_rate_limits_are_not_retried_in_legacy_mode(error_name):
    from app.inference import contracts

    primary = StubProvider(
        "freellmapi",
        [getattr(contracts, error_name)("freellmapi", "unavailable")],
    )
    with pytest.raises(InferenceTimeoutError):
        _ = [chunk async for chunk in stream_response(request(), primary=primary)]
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_persistent_first_token_timeout_stops_after_two_attempts():
    primary = StubProvider(
        "freellmapi",
        [InferenceTimeoutError("freellmapi", "unavailable")],
    )
    with pytest.raises(InferenceTimeoutError):
        _ = [chunk async for chunk in stream_response(request(), primary=primary)]
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_explicit_pool_moves_to_next_model_after_first_token_timeout():
    primary = ModelAwareProvider(
        {
            "model-a": "slow",
            "model-b": ["rápido"],
        }
    )

    chunks = [
        chunk
        async for chunk in stream_response(
            request(),
            primary=primary,
            primary_models=("model-a", "model-b"),
            first_token_timeout_seconds=0.01,
        )
    ]

    assert chunks == [
        StreamChunk(provider="freellmapi", text="rápido", model="model-b")
    ]
    assert primary.models == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_explicit_pool_moves_to_next_model_after_rate_limit():
    primary = ModelAwareProvider(
        {
            "model-a": [
                InferenceRateLimitError("freellmapi", "model-a rate limited")
            ],
            "model-b": ["resposta"],
        }
    )

    chunks = [
        chunk
        async for chunk in stream_response(
            request(),
            primary=primary,
            primary_models=("model-a", "model-b"),
        )
    ]

    assert chunks == [
        StreamChunk(provider="freellmapi", text="resposta", model="model-b")
    ]
    assert primary.models == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_provider_fallback_uses_its_own_default_after_pool_is_exhausted():
    primary = ModelAwareProvider(
        {
            "model-a": [
                InferenceRateLimitError("freellmapi", "model-a rate limited")
            ],
            "model-b": [
                InferenceTimeoutError("freellmapi", "model-b timeout")
            ],
        }
    )
    fallback = StubProvider(
        "anthropic",
        ["reserva"],
        default_model="claude-model",
    )

    chunks = [
        chunk
        async for chunk in stream_response(
            request(),
            primary=primary,
            primary_models=("model-a", "model-b"),
            fallbacks=(fallback,),
        )
    ]

    assert chunks == [
        StreamChunk(provider="anthropic", text="reserva", model="claude-model")
    ]
    assert primary.models == ["model-a", "model-b"]
    assert fallback.calls == 1
    assert fallback.requests[0].model is None


@pytest.mark.asyncio
async def test_provider_fallback_is_used_after_primary_rate_limit_without_pool():
    primary = StubProvider(
        "freellmapi",
        [InferenceRateLimitError("freellmapi", "rate limited")],
    )
    fallback = StubProvider("anthropic", ["reserva"])

    chunks = [
        chunk
        async for chunk in stream_response(
            request(),
            primary=primary,
            fallbacks=(fallback,),
        )
    ]

    assert chunks == [
        StreamChunk(provider="anthropic", text="reserva", model=None)
    ]
    assert primary.calls == 1
    assert fallback.calls == 1
