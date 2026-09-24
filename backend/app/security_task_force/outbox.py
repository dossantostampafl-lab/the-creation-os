from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .events import STFEvent


@dataclass
class OutboxItem:
    event: STFEvent
    published: bool = False


async def publish_pending(items: list[OutboxItem], publish: Callable[[STFEvent], Awaitable[None]]) -> None:
    for item in items:
        if item.published:
            continue
        await publish(item.event)
        item.published = True
