from __future__ import annotations

from typing import Any, Protocol

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
)
from app.capabilities.policy import CapabilityDeclaration, authorize_capability, declaration_for


class CapabilityAdapter(Protocol):
    name: str
    # What running this does, declared by the adapter rather than by the model's request.
    external_effect: bool
    minimum_idempotency_class: IdempotencyClass

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult: ...


class CapabilityGateway:
    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def declaration(self, capability: str) -> CapabilityDeclaration:
        """What the registered adapter says it does — the most dangerous case when none is."""
        return declaration_for(self._adapters.get(capability))

    def register(self, adapter: CapabilityAdapter) -> None:
        if adapter.name in self._adapters:
            raise ValueError(f"capability adapter already registered: {adapter.name}")
        self._adapters[adapter.name] = adapter

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        """Run a capability for one Mission, after its authorization allows the request."""
        adapter = self._adapters.get(intent.capability)
        # The adapter is looked up first only to read its declaration; policy still decides,
        # and an unauthorized capability is denied whether or not an adapter exists.
        authorize_capability(intent, context.authorization, self.declaration(intent.capability))
        if adapter is None:
            raise LookupError(f"capability adapter unavailable: {intent.capability}")
        return await adapter.execute(intent, context)
