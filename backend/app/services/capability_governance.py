from __future__ import annotations

from dataclasses import dataclass

from app.automation.contracts import ConnectorRejected
from app.automation.registry import ConnectorRegistry, default_registry
from app.capabilities.contracts import CAPABILITY_FRAMEWORK_VERSION, CapabilityDefinition
from app.capabilities.registry import CapabilityRegistry, default_capability_registry
from app.core.domain import Actor, DomainError
from app.models.capability_registry import RegisteredCapability
from app.repositories.capabilities import CapabilityRepository
from app.services.capabilities import CapabilityPersistenceService


class CapabilityGovernanceError(DomainError):
    pass


class CAPABILITY_NOT_REGISTERED(CapabilityGovernanceError):
    pass


class CAPABILITY_DISABLED(CapabilityGovernanceError):
    pass


class CAPABILITY_DEPENDENCY_MISSING(CapabilityGovernanceError):
    pass


class CAPABILITY_DEPENDENCY_DISABLED(CapabilityGovernanceError):
    pass


class CAPABILITY_DEPENDENCY_CYCLE(CapabilityGovernanceError):
    pass


class CAPABILITY_PERMISSION_DENIED(CapabilityGovernanceError):
    pass


class CONNECTOR_UNAVAILABLE(CapabilityGovernanceError):
    pass


@dataclass(frozen=True)
class CapabilityAuthorization:
    capability: CapabilityDefinition
    persisted: RegisteredCapability
    framework_version: str = CAPABILITY_FRAMEWORK_VERSION


class CapabilityGovernanceService:
    def __init__(
        self,
        repository: CapabilityRepository,
        *,
        capability_registry: CapabilityRegistry | None = None,
        connector_registry: ConnectorRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.capability_registry = capability_registry or default_capability_registry()
        self.connector_registry = connector_registry or default_registry()

    async def authorize_execution(
        self,
        actor: Actor,
        *,
        connector_id: str,
        connector_capability: str,
        correlation_id: str,
    ) -> CapabilityAuthorization:
        capability: CapabilityDefinition | None = None
        try:
            self._ensure_creator(actor)
            capability = self._definition_for_connector(connector_id, connector_capability)
            await CapabilityPersistenceService(self.repository, self.capability_registry)._sync_definitions()
            persisted = await self.repository.by_capability_id(capability.capability_id)
            if persisted is None:
                raise CAPABILITY_NOT_REGISTERED(f"Capability is not registered: {capability.capability_id}")
            if not persisted.enabled:
                raise CAPABILITY_DISABLED(f"Capability is disabled: {capability.capability_id}")
            persisted_by_id = {item.capability_id: item for item in await self.repository.list()}
            definition_by_id = {item.capability_id: item for item in self.capability_registry.discover()}
            self._validate_dependencies(capability, definition_by_id, persisted_by_id, [])
            self._validate_connector(connector_id, connector_capability)
            await self._audit("capability.execution.authorized", actor, correlation_id, capability, {"authorized": True})
            await self.repository.commit()
            return CapabilityAuthorization(capability=capability, persisted=persisted)
        except CapabilityGovernanceError as exc:
            await self.repository.rollback()
            await self._audit(
                "capability.execution.denied",
                actor,
                correlation_id,
                capability,
                {"authorized": False, "code": exc.__class__.__name__},
            )
            await self.repository.commit()
            raise

    def _ensure_creator(self, actor: Actor) -> None:
        if actor.role != "creator":
            raise CAPABILITY_PERMISSION_DENIED("Only Creator may execute capabilities")

    def _definition_for_connector(self, connector_id: str, connector_capability: str) -> CapabilityDefinition:
        for definition in self.capability_registry.discover():
            if definition.connector_id == connector_id and definition.connector_capability == connector_capability:
                return definition
        raise CAPABILITY_NOT_REGISTERED(f"Capability is not registered: {connector_id}.{connector_capability}")

    def _validate_dependencies(
        self,
        capability: CapabilityDefinition,
        definitions: dict[str, CapabilityDefinition],
        persisted: dict[str, RegisteredCapability],
        stack: list[str],
    ) -> None:
        if capability.capability_id in stack:
            cycle = " -> ".join([*stack, capability.capability_id])
            raise CAPABILITY_DEPENDENCY_CYCLE(f"Capability dependency cycle detected: {cycle}")
        next_stack = [*stack, capability.capability_id]
        for dependency_id in capability.dependencies:
            dependency_definition = definitions.get(dependency_id)
            if dependency_definition is None:
                raise CAPABILITY_DEPENDENCY_MISSING(f"Capability dependency is missing: {dependency_id}")
            dependency_state = persisted.get(dependency_id)
            if dependency_state is None:
                raise CAPABILITY_DEPENDENCY_MISSING(f"Capability dependency is not registered: {dependency_id}")
            if not dependency_state.enabled:
                raise CAPABILITY_DEPENDENCY_DISABLED(f"Capability dependency is disabled: {dependency_id}")
            self._validate_dependencies(dependency_definition, definitions, persisted, next_stack)

    def _validate_connector(self, connector_id: str, connector_capability: str) -> None:
        try:
            self.connector_registry.capability(connector_id, connector_capability)
        except ConnectorRejected as exc:
            raise CONNECTOR_UNAVAILABLE(f"Connector is unavailable: {connector_id}.{connector_capability}") from exc

    async def _audit(
        self,
        event_type: str,
        actor: Actor,
        correlation_id: str,
        capability: CapabilityDefinition | None,
        payload: dict,
    ) -> None:
        safe_payload = {
            "capability_id": capability.capability_id if capability else None,
            "connector_id": capability.connector_id if capability else None,
            "connector_capability": capability.connector_capability if capability else None,
            **payload,
        }
        await self.repository.add_event(
            capability.capability_id if capability else "unknown",
            actor.id,
            actor.role,
            correlation_id,
            safe_payload,
            event_type=event_type,
        )
