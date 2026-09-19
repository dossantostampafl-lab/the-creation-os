from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

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


class IdempotencyClass(StrEnum):
    SAFE = "SAFE"
    IDEMPOTENT = "IDEMPOTENT"
    AT_MOST_ONCE = "AT_MOST_ONCE"


class CapabilityIntent(BaseModel):
    capability: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., min_length=1, max_length=128)
    resource: str | None = Field(default=None, max_length=512)
    arguments: dict[str, Any] = Field(default_factory=dict)
    external_effect: bool = False
    idempotency_class: IdempotencyClass = IdempotencyClass.SAFE
    idempotency_key: str | None = Field(default=None, max_length=256)


class MissionAuthorization(BaseModel):
    allowed_capabilities: list[str] = Field(default_factory=list)
    denied_capabilities: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    external_effects_allowed: bool = False
    risk_level: str = "low"
    budget: dict[str, Any] = Field(default_factory=dict)
    expires_at: str | None = None
    version: int = Field(default=1, ge=1)
    authorized_by: str
    authorized_at: str


class CapabilityResult(BaseModel):
    capability: str
    action: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
