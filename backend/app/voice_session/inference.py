from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.inference.contracts import InferenceError, InferenceRequest, InferenceTimeoutError


class StreamingProvider(Protocol):
    name: str

    def stream(self, request: InferenceRequest) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class StreamChunk:
    provider: str
    text: str


async def _stream_with_first_token_deadline(
    request: InferenceRequest,
    provider: StreamingProvider,
    *,
    timeout_seconds: float,
) -> AsyncIterator[StreamChunk]:
    stream = provider.stream(request).__aiter__()
    try:
        first_text = await asyncio.wait_for(
            stream.__anext__(),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise InferenceTimeoutError(
            provider.name,
            f"{provider.name} first-token timeout",
        ) from exc
    except StopAsyncIteration:
        return

    if first_text:
        yield StreamChunk(provider=provider.name, text=first_text)

    async for text in stream:
        if text:
            yield StreamChunk(provider=provider.name, text=text)


async def stream_with_fallback(
    request: InferenceRequest,
    *,
    primary: StreamingProvider,
    fallback: StreamingProvider,
    first_token_timeout_seconds: float = 2.5,
) -> AsyncIterator[StreamChunk]:
    if first_token_timeout_seconds <= 0:
        raise ValueError("first_token_timeout_seconds must be greater than zero")

    primary_stream = primary.stream(request).__aiter__()
    try:
        first_text = await asyncio.wait_for(
            primary_stream.__anext__(),
            timeout=first_token_timeout_seconds,
        )
    except (TimeoutError, InferenceError, StopAsyncIteration):
        async for chunk in _stream_with_first_token_deadline(
            request,
            fallback,
            timeout_seconds=first_token_timeout_seconds,
        ):
            yield chunk
        return

    if first_text:
        yield StreamChunk(provider=primary.name, text=first_text)

    async for text in primary_stream:
        if text:
            yield StreamChunk(provider=primary.name, text=text)
