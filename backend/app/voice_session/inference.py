from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
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


@traced("llm.stream.step")
async def stream_response(
    request: InferenceRequest,
    *,
    primary: StreamingProvider,
    first_token_timeout_seconds: float = 2.5,
) -> AsyncIterator[StreamChunk]:
    if first_token_timeout_seconds <= 0:
        raise ValueError("first_token_timeout_seconds must be greater than zero")

    # The free upstream can miss a deadline transiently. Retry only before any
    # response text exists, and never retry authentication or rate-limit errors.
    for attempt in range(2):
        primary_stream = primary.stream(request).__aiter__()
        try:
            with operation("llm.stream.attempt", {"creation.provider": primary.name}):
                first_text = await asyncio.wait_for(
                    primary_stream.__anext__(),
                    timeout=first_token_timeout_seconds,
                )
            break
        except (TimeoutError, InferenceTimeoutError) as exc:
            if attempt == 0:
                continue
            raise InferenceTimeoutError(primary.name, "FreeLLM voice response unavailable") from exc
        except (InferenceError, StopAsyncIteration) as exc:
            raise InferenceTimeoutError(primary.name, "FreeLLM voice response unavailable") from exc

    if first_text:
        yield StreamChunk(provider=primary.name, text=first_text)

    async for text in primary_stream:
        if text:
            yield StreamChunk(provider=primary.name, text=text)
