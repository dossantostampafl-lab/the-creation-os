from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ConnectorStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ConnectorCapability:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ConnectorRequest:
    connector_id: str
    capability: str
    payload: dict[str, Any]
    timeout_seconds: float
    idempotency_key: str
    correlation_id: str


@dataclass(frozen=True)
class ConnectorResult:
    status: ConnectorStatus
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class ConnectorError(Exception):
    code = "connector_error"


class ConnectorRejected(ConnectorError):
    code = "connector_rejected"


class ConnectorTimeout(ConnectorError):
    code = "connector_timeout"


class Connector(Protocol):
    connector_id: str

    def capabilities(self) -> list[ConnectorCapability]:
        raise NotImplementedError

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        raise NotImplementedError
