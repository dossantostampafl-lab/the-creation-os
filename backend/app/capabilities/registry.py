from __future__ import annotations

from dataclasses import replace

from app.capabilities.contracts import (
    CAPABILITY_ID_PATTERN,
    SEMVER_PATTERN,
    CapabilityDefinition,
    CapabilityPermission,
    CapabilityValidation,
)
from app.core.domain import DomainError


class CapabilityError(DomainError):
    pass


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._connector_index: dict[tuple[str, str], str] = {}

    def register(self, capability: CapabilityDefinition) -> None:
        self._validate_definition(capability)
        if capability.capability_id in self._capabilities:
            raise CapabilityError(f"Capability already registered: {capability.capability_id}")
        key = (capability.connector_id, capability.connector_capability)
        if key in self._connector_index:
            raise CapabilityError(f"Connector capability already mapped: {capability.connector_id}.{capability.connector_capability}")
        self._capabilities[capability.capability_id] = capability
        self._connector_index[key] = capability.capability_id

    def discover(self) -> list[CapabilityDefinition]:
        return [self._capabilities[key] for key in sorted(self._capabilities)]

    def get(self, capability_id: str) -> CapabilityDefinition:
        item = self._capabilities.get(capability_id)
        if item is None:
            raise CapabilityError(f"Unknown Capability: {capability_id}")
        return item

    def enable(self, capability_id: str) -> CapabilityDefinition:
        item = replace(self.get(capability_id), enabled=True)
        self._capabilities[capability_id] = item
        return item

    def disable(self, capability_id: str) -> CapabilityDefinition:
        item = replace(self.get(capability_id), enabled=False)
        self._capabilities[capability_id] = item
        return item

    def validate_execution(self, connector_id: str, connector_capability: str) -> CapabilityValidation:
        capability_id = self._connector_index.get((connector_id, connector_capability))
        if capability_id is None:
            raise CapabilityError(f"Connector capability is not registered as a Capability: {connector_id}.{connector_capability}")
        capability = self.get(capability_id)
        if not capability.enabled:
            raise CapabilityError(f"Capability is disabled: {capability.capability_id}")
        for dependency in capability.dependencies:
            dependency_item = self.get(dependency)
            if not dependency_item.enabled:
                raise CapabilityError(f"Capability dependency is disabled: {dependency}")
        return CapabilityValidation(capability=capability)

    def _validate_definition(self, capability: CapabilityDefinition) -> None:
        if not CAPABILITY_ID_PATTERN.fullmatch(capability.capability_id):
            raise CapabilityError("Capability id is invalid")
        if not SEMVER_PATTERN.fullmatch(capability.version):
            raise CapabilityError("Capability version must be semantic")
        if not capability.name.strip() or not capability.description.strip():
            raise CapabilityError("Capability name and description are required")
        if not capability.connector_id.strip() or not capability.connector_capability.strip():
            raise CapabilityError("Capability connector mapping is required")
        if not capability.permissions:
            raise CapabilityError("Capability must declare at least one permission")
        if len(capability.dependencies) != len(set(capability.dependencies)):
            raise CapabilityError("Capability dependencies must be unique")
        if capability.capability_id in capability.dependencies:
            raise CapabilityError("Capability cannot depend on itself")


def github_capabilities() -> list[CapabilityDefinition]:
    return [
        CapabilityDefinition(
            capability_id="github.repositories.list",
            name="GitHub Authorized Repository Discovery",
            description="Lists GitHub repositories explicitly authorized for THE CREATION OS.",
            version="1.0.0",
            connector_id="github",
            connector_capability="list_authorized_repositories",
            enabled=True,
            permissions=(CapabilityPermission.READ,),
            metadata={"provider": "github", "destructive": "false"},
        ),
        CapabilityDefinition(
            capability_id="github.issues.read",
            name="GitHub Issue Reader",
            description="Reads issues from an authorized GitHub repository.",
            version="1.0.0",
            connector_id="github",
            connector_capability="list_issues",
            enabled=True,
            permissions=(CapabilityPermission.READ,),
            dependencies=("github.repositories.list",),
            metadata={"provider": "github", "destructive": "false"},
        ),
        CapabilityDefinition(
            capability_id="github.pull_requests.read",
            name="GitHub Pull Request Reader",
            description="Reads pull requests from an authorized GitHub repository.",
            version="1.0.0",
            connector_id="github",
            connector_capability="list_pull_requests",
            enabled=True,
            permissions=(CapabilityPermission.READ,),
            dependencies=("github.repositories.list",),
            metadata={"provider": "github", "destructive": "false"},
        ),
        CapabilityDefinition(
            capability_id="github.issues.create",
            name="GitHub Issue Creator",
            description="Creates a non-destructive issue in an authorized GitHub repository.",
            version="1.0.0",
            connector_id="github",
            connector_capability="create_issue",
            enabled=True,
            permissions=(CapabilityPermission.WRITE,),
            dependencies=("github.repositories.list",),
            metadata={"provider": "github", "destructive": "false"},
        ),
        CapabilityDefinition(
            capability_id="github.issues.comment",
            name="GitHub Issue Commenter",
            description="Adds a non-destructive comment to an existing GitHub issue.",
            version="1.0.0",
            connector_id="github",
            connector_capability="add_issue_comment",
            enabled=True,
            permissions=(CapabilityPermission.COMMENT,),
            dependencies=("github.repositories.list",),
            metadata={"provider": "github", "destructive": "false"},
        ),
        CapabilityDefinition(
            capability_id="github.workflows.status",
            name="GitHub Workflow Status Reader",
            description="Reads workflow run status from an authorized GitHub repository without executing workflows.",
            version="1.0.0",
            connector_id="github",
            connector_capability="list_workflow_runs",
            enabled=True,
            permissions=(CapabilityPermission.STATUS,),
            dependencies=("github.repositories.list",),
            metadata={"provider": "github", "destructive": "false", "executes_workflow": "false"},
        ),
    ]


def rest_capabilities() -> list[CapabilityDefinition]:
    return [
        CapabilityDefinition(
            capability_id="rest.restricted.request",
            name="Restricted REST Request",
            description="Executes a restricted outbound REST request to pre-authorized public hosts.",
            version="1.0.0",
            connector_id="restricted_rest",
            connector_capability="http_request",
            enabled=True,
            permissions=(CapabilityPermission.NETWORK,),
            metadata={"provider": "rest", "destructive": "false"},
        )
    ]


def default_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for capability in [*github_capabilities(), *rest_capabilities()]:
        registry.register(capability)
    return registry
