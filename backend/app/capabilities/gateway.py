from __future__ import annotations

from typing import Any, Protocol

from app.capabilities.contracts import CapabilityIntent, CapabilityResult, MissionAuthorization
from app.capabilities.policy import authorize_capability


class CapabilityAdapter(Protocol):
    name: str

    async def execute(self, intent: CapabilityIntent) -> CapabilityResult: ...


class CapabilityGateway:
    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, adapter: CapabilityAdapter) -> None:
        if adapter.name in self._adapters:
            raise ValueError(f"capability adapter already registered: {adapter.name}")
        self._adapters[adapter.name] = adapter

    async def execute(self, intent: CapabilityIntent, authorization: MissionAuthorization) -> CapabilityResult:
        authorize_capability(intent, authorization)
        adapter = self._adapters.get(intent.capability)
        if adapter is None:
            raise LookupError(f"capability adapter unavailable: {intent.capability}")
        return await adapter.execute(intent)
