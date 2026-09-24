from __future__ import annotations

from typing import Any, Protocol

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
)
from app.capabilities.policy import authorize_capability


class CapabilityAdapter(Protocol):
    name: str

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult: ...


class CapabilityGateway:
    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, adapter: CapabilityAdapter) -> None:
        if adapter.name in self._adapters:
            raise ValueError(f"capability adapter already registered: {adapter.name}")
        self._adapters[adapter.name] = adapter

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        """Run a capability for one Mission, after its authorization allows the request."""
        authorize_capability(intent, context.authorization)
        adapter = self._adapters.get(intent.capability)
        if adapter is None:
            raise LookupError(f"capability adapter unavailable: {intent.capability}")
        return await adapter.execute(intent, context)
