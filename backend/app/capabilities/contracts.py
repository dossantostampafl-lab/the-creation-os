from __future__ import annotations

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


@dataclass(frozen=True)
class CapabilityValidation:
    capability: CapabilityDefinition
    framework_version: str = CAPABILITY_FRAMEWORK_VERSION
