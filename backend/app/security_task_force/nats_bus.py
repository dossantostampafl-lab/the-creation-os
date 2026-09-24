from __future__ import annotations

import json
from typing import Any

from .events import STFEvent


class EventBus:
    def __init__(self, nc: Any) -> None:
        self.nc = nc

    async def publish(self, subject: str, value: STFEvent) -> None:
        payload = json.dumps(value.model_dump(mode="json"), sort_keys=True).encode()
        js = self.nc.jetstream()
        await js.publish(subject, payload, headers={"Nats-Msg-Id": value.event_id})
