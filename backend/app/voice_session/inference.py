from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.inference.contracts import InferenceError, InferenceRequest, InferenceTimeoutError
from app.observability.telemetry import operation, traced


class StreamingProvider(Protocol):
    name: str

    def stream(self, request: InferenceRequest) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class StreamChunk:
    provider: str
    text: str
    model: str | None = None


def _resolved_model(provider: StreamingProvider, request: InferenceRequest) -> str | None:
    if request.model:
        return request.model
    public_default = getattr(provider, "default_model", None)
    if isinstance(public_default, str) and public_default.strip():
        return public_default
    private_default = getattr(provider, "_default_model", None)
    if isinstance(private_default, str) and private_default.strip():
        return private_default
    return None


async def _open_stream(
    provider: StreamingProvider,
    request: InferenceRequest,
    *,
    first_token_timeout_seconds: float,
) -> tuple[str, AsyncIterator[str]]:
    provider_stream = provider.stream(request).__aiter__()
    try:
        first_text = await asyncio.wait_for(
            provider_stream.__anext__(),
            timeout=first_token_timeout_seconds,
        )
    except TimeoutError as exc:
        close = getattr(provider_stream, "aclose", None)
        if close is not None:
            await close()
        raise InferenceTimeoutError(
            provider.name,
            f"{provider.name} voice first token timed out",
        ) from exc
    except StopAsyncIteration as exc:
        raise InferenceTimeoutError(
            provider.name,
            f"{provider.name} voice stream ended before the first token",
        ) from exc
    return first_text, provider_stream


async def _serve_attempt(
    provider: StreamingProvider,
    request: InferenceRequest,
    *,
    first_token_timeout_seconds: float,
) -> AsyncIterator[StreamChunk]:
    model = _resolved_model(provider, request)
    with operation(
        "llm.stream.attempt",
        {
            "creation.provider": provider.name,
            "creation.model": model or "provider-default",
        },
    ):
        first_text, provider_stream = await _open_stream(
            provider,
            request,
            first_token_timeout_seconds=first_token_timeout_seconds,
        )

    if first_text:
        yield StreamChunk(provider=provider.name, text=first_text, model=model)

    async for text in provider_stream:
        if text:
            yield StreamChunk(provider=provider.name, text=text, model=model)


@traced("llm.stream.step")
async def stream_response(
    request: InferenceRequest,
    *,
    primary: StreamingProvider,
    primary_models: Sequence[str] = (),
    fallbacks: Sequence[StreamingProvider] = (),
    first_token_timeout_seconds: float = 2.5,
    first_token_timeouts_by_provider: Mapping[str, float] | None = None,
) -> AsyncIterator[StreamChunk]:
    """Stream one coherent answer, failing over only before any model text is emitted.

    With no explicit model pool this preserves the old FreeLLM behavior: one
    transient first-token timeout is retried on the same provider. When a pool
    is configured, each explicit FreeLLM model is tried once in order. Provider
    fallbacks use their own default model and are reached only after the FreeLLM
    attempts have failed before the first token.
    """
    if first_token_timeout_seconds <= 0:
        raise ValueError("first_token_timeout_seconds must be greater than zero")
    timeouts = first_token_timeouts_by_provider or {}
    if any(timeout <= 0 for timeout in timeouts.values()):
        raise ValueError("provider first token timeouts must be greater than zero")

    models = tuple(model.strip() for model in primary_models if model.strip())
    primary_requests = (
        tuple(request.model_copy(update={"model": model}) for model in models)
        if models
        else (request, request) if primary.name == "freellmapi" else (request,)
    )

    last_error: InferenceError | None = None
    for attempt_index, attempt_request in enumerate(primary_requests):
        emitted = False
        try:
            async for chunk in _serve_attempt(
                primary,
                attempt_request,
                first_token_timeout_seconds=timeouts.get(primary.name, first_token_timeout_seconds),
            ):
                emitted = True
                yield chunk
            return
        except InferenceError as exc:
            if emitted:
                raise
            last_error = exc
            # Legacy mode retries only transient first-token timeouts. An
            # explicit model pool intentionally advances on any pre-token
            # provider error so a bad/rate-limited model cannot pin the turn.
            if not models and (
                not isinstance(exc, InferenceTimeoutError)
                or attempt_index + 1 >= len(primary_requests)
            ):
                break

    fallback_request = request.model_copy(update={"model": None})
    for fallback in fallbacks:
        emitted = False
        try:
            async for chunk in _serve_attempt(
                fallback,
                fallback_request,
                first_token_timeout_seconds=timeouts.get(fallback.name, first_token_timeout_seconds),
            ):
                emitted = True
                yield chunk
            return
        except InferenceError as exc:
            if emitted:
                raise
            last_error = exc
            continue

    if last_error is not None:
        # Preserve the legacy single-provider contract for callers that have
        # not enabled the new policy yet.
        if (
            not models
            and not fallbacks
            and not isinstance(last_error, InferenceTimeoutError)
        ):
            raise InferenceTimeoutError(
                primary.name,
                "FreeLLM voice response unavailable",
            ) from last_error
        raise last_error
    raise InferenceTimeoutError(primary.name, "DEUS voice inference is unavailable")
