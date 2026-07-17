from __future__ import annotations

from app.automation.connectors.github import GitHubConnector
from app.automation.connectors.opportunity import OpportunityConnector
from app.automation.connectors.rest import RestrictedRestConnector
from app.automation.contracts import Connector, ConnectorCapability, ConnectorRejected


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        if connector.connector_id in self._connectors:
            raise ConnectorRejected(f"Connector already registered: {connector.connector_id}")
        capabilities = connector.capabilities()
        if not capabilities:
            raise ConnectorRejected("Connector must expose at least one capability")
        names = [capability.name for capability in capabilities]
        if len(names) != len(set(names)):
            raise ConnectorRejected("Connector capability names must be unique")
        self._connectors[connector.connector_id] = connector

    def get(self, connector_id: str) -> Connector:
        connector = self._connectors.get(connector_id)
        if connector is None:
            raise ConnectorRejected(f"Unknown connector: {connector_id}")
        return connector

    def capability(self, connector_id: str, capability_name: str) -> ConnectorCapability:
        connector = self.get(connector_id)
        for capability in connector.capabilities():
            if capability.name == capability_name:
                return capability
        raise ConnectorRejected(f"Unsupported capability for connector {connector_id}: {capability_name}")

    def list_capabilities(self) -> dict[str, list[ConnectorCapability]]:
        return {connector_id: connector.capabilities() for connector_id, connector in sorted(self._connectors.items())}


def default_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(
        RestrictedRestConnector(
            allowed_hosts={"api.creation.local", "example.com"},
            allowed_methods={"GET", "POST"},
            max_response_bytes=65536,
        )
    )
    registry.register(GitHubConnector())
    registry.register(OpportunityConnector())
    return registry
