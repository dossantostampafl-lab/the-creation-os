from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from .events import STFEvent

STREAM = "STF"
SUBJECT_PREFIX = "stf"
DEAD_LETTER_SUBJECT = "stf.dlq"
DUPLICATE_WINDOW_SECONDS = 120


def subject_for(event_type: str) -> str:
    return f"{SUBJECT_PREFIX}.{event_type}"


class EventBus:
    """Publishes versioned events to JetStream. The message id is the event id, so a retried
    publish of the same event is dropped by the server instead of doubling downstream effects."""

    def __init__(self, nc: Any) -> None:
        self.nc = nc

    async def ensure_stream(self) -> None:
        jetstream = self.nc.jetstream()
        await jetstream.add_stream(
            name=STREAM,
            subjects=[f"{SUBJECT_PREFIX}.>"],
            duplicate_window=DUPLICATE_WINDOW_SECONDS,
        )

    async def publish(self, value: STFEvent) -> None:
        payload = json.dumps(value.model_dump(mode="json"), sort_keys=True).encode()
        await self.nc.jetstream().publish(
            subject_for(value.event_type), payload, headers={"Nats-Msg-Id": value.event_id}
        )

    async def dead_letter(self, raw: bytes, reason: str) -> None:
        await self.nc.jetstream().publish(DEAD_LETTER_SUBJECT, raw, headers={"Stf-Dead-Letter-Reason": reason})


class IdempotentConsumer:
    """Applies each event id once. A malformed or unknown event goes to the dead-letter subject
    instead of blocking the stream, and a handler failure leaves the id unmarked so it is retried."""

    def __init__(self, handler: Callable[[STFEvent], Awaitable[None]], bus: EventBus, *, processed: set[str] | None = None) -> None:
        self._handler = handler
        self._bus = bus
        self._processed = processed if processed is not None else set()

    async def handle(self, raw: bytes) -> str:
        try:
            value = STFEvent.model_validate(json.loads(raw))
        except (ValueError, ValidationError):
            await self._bus.dead_letter(raw, "poison")
            return "dead_lettered"
        if value.event_id in self._processed:
            return "duplicate"
        await self._handler(value)
        self._processed.add(value.event_id)
        return "processed"
