from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum

CAPABILITY_FRAMEWORK_VERSION = "v1.6.0"
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class CapabilityPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    COMMENT = "comment"
    STATUS = "status"
    NETWORK = "network"


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    name: str
    description: str
    version: str
    connector_id: str
    connector_capability: str
    enabled: bool
    permissions: tuple[CapabilityPermission, ...]
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, str] = field(default_factory=dict)
    mandatory: bool = False


@dataclass(frozen=True)
class CapabilityValidation:
    capability: CapabilityDefinition
    framework_version: str = CAPABILITY_FRAMEWORK_VERSION


def capability_fingerprint(capability: CapabilityDefinition) -> str:
    material = {
        "schema_version": "1.0",
        "framework_version": CAPABILITY_FRAMEWORK_VERSION,
        "capability_id": capability.capability_id,
        "name": capability.name,
        "description": capability.description,
        "version": capability.version,
        "connector_id": capability.connector_id,
        "connector_capability": capability.connector_capability,
        "permissions": [permission.value for permission in capability.permissions],
        "dependencies": list(capability.dependencies),
        "metadata": capability.metadata,
        "mandatory": capability.mandatory,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
