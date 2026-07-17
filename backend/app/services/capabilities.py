from __future__ import annotations

from app.capabilities.contracts import CapabilityDefinition, capability_fingerprint
from app.capabilities.registry import CapabilityError, CapabilityRegistry, default_capability_registry
from app.core.domain import Actor, require_creator
from app.models.capability_registry import RegisteredCapability
from app.repositories.capabilities import CapabilityRepository


class CapabilityPersistenceService:
    def __init__(
        self,
        repository: CapabilityRepository,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or default_capability_registry()

    async def sync(self) -> list[RegisteredCapability]:
        await self._sync_definitions()
        await self.repository.commit()
        return await self.repository.list()

    async def list(self, actor: Actor) -> list[RegisteredCapability]:
        require_creator(actor, "list capabilities")
        await self.sync()
        return await self.repository.list()

    async def enable(self, actor: Actor, capability_id: str, correlation_id: str) -> RegisteredCapability:
        require_creator(actor, "enable capability")
        await self._sync_definitions()
        item = await self.repository.by_capability_id(capability_id, lock=True)
        if item is None:
            await self.repository.rollback()
            raise CapabilityError(f"Unknown Capability: {capability_id}")
        if item.enabled:
            await self.repository.commit()
            return item
        item.enabled = True
        await self.repository.flush()
        await self.repository.add_event(
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"capability_id": item.capability_id, "enabled": True, "mandatory": item.mandatory},
        )
        await self.repository.commit()
        return item

    async def disable(self, actor: Actor, capability_id: str, correlation_id: str) -> RegisteredCapability:
        require_creator(actor, "disable capability")
        await self._sync_definitions()
        item = await self.repository.by_capability_id(capability_id, lock=True)
        if item is None:
            await self.repository.rollback()
            raise CapabilityError(f"Unknown Capability: {capability_id}")
        if item.mandatory:
            await self.repository.rollback()
            raise CapabilityError(f"Mandatory Capability cannot be disabled: {capability_id}")
        if not item.enabled:
            await self.repository.commit()
            return item
        item.enabled = False
        await self.repository.flush()
        await self.repository.add_event(
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"capability_id": item.capability_id, "enabled": False, "mandatory": item.mandatory},
        )
        await self.repository.commit()
        return item

    async def synced_registry(self) -> CapabilityRegistry:
        await self._sync_definitions()
        await self.repository.commit()
        persisted = {item.capability_id: item for item in await self.repository.list()}
        registry = CapabilityRegistry()
        for definition in self.registry.discover():
            item = persisted[definition.capability_id]
            registry.register(self._definition_with_state(definition, item.enabled))
        return registry

    async def _sync_definitions(self) -> None:
        for definition in self.registry.discover():
            await self._sync_definition(definition)

    async def _sync_definition(self, definition: CapabilityDefinition) -> RegisteredCapability:
        item = await self.repository.by_capability_id(definition.capability_id)
        fingerprint = capability_fingerprint(definition)
        permissions = [permission.value for permission in definition.permissions]
        dependencies = list(definition.dependencies)
        if item is None:
            return await self.repository.add(
                RegisteredCapability(
                    capability_id=definition.capability_id,
                    name=definition.name,
                    description=definition.description,
                    version=definition.version,
                    connector_id=definition.connector_id,
                    connector_capability=definition.connector_capability,
                    enabled=definition.enabled,
                    mandatory=definition.mandatory,
                    permissions_json=permissions,
                    dependencies_json=dependencies,
                    metadata_json=definition.metadata,
                    capability_fingerprint=fingerprint,
                )
            )
        item.name = definition.name
        item.description = definition.description
        item.version = definition.version
        item.connector_id = definition.connector_id
        item.connector_capability = definition.connector_capability
        item.mandatory = definition.mandatory
        item.permissions_json = permissions
        item.dependencies_json = dependencies
        item.metadata_json = definition.metadata
        item.capability_fingerprint = fingerprint
        await self.repository.flush()
        return item

    def _definition_with_state(self, definition: CapabilityDefinition, enabled: bool) -> CapabilityDefinition:
        return CapabilityDefinition(
            capability_id=definition.capability_id,
            name=definition.name,
            description=definition.description,
            version=definition.version,
            connector_id=definition.connector_id,
            connector_capability=definition.connector_capability,
            enabled=enabled,
            permissions=definition.permissions,
            dependencies=definition.dependencies,
            metadata=definition.metadata,
            mandatory=definition.mandatory,
        )
