from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.automation.contracts import ConnectorRejected, ConnectorRequest, ConnectorResult, ConnectorStatus
from app.automation.registry import ConnectorRegistry

AUTOMATION_POLICY_VERSION = "v1.5.0"


@dataclass(frozen=True)
class AutomationExecutionDocument:
    request_fingerprint: str
    result: ConnectorResult


def canonical_payload(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_fingerprint(request: ConnectorRequest) -> str:
    material = {
        "schema_version": "1.0",
        "policy_version": AUTOMATION_POLICY_VERSION,
        "connector_id": request.connector_id,
        "capability": request.capability,
        "payload": request.payload,
        "timeout_seconds": request.timeout_seconds,
        "idempotency_key": request.idempotency_key,
    }
    return hashlib.sha256(canonical_payload(material).encode("utf-8")).hexdigest()


class AutomationExecutor:
    def __init__(self, registry: ConnectorRegistry) -> None:
        self.registry = registry

    async def execute(self, request: ConnectorRequest) -> AutomationExecutionDocument:
        fingerprint = request_fingerprint(request)
        try:
            self.registry.capability(request.connector_id, request.capability)
            connector = self.registry.get(request.connector_id)
            result = await asyncio.wait_for(connector.execute(request), timeout=request.timeout_seconds)
            return AutomationExecutionDocument(request_fingerprint=fingerprint, result=result)
        except asyncio.TimeoutError:
            return AutomationExecutionDocument(
                request_fingerprint=fingerprint,
                result=ConnectorResult(
                    status=ConnectorStatus.TIMEOUT,
                    error_code="connector_timeout",
                    error_message="Connector execution exceeded timeout",
                ),
            )
        except ConnectorRejected as exc:
            return AutomationExecutionDocument(
                request_fingerprint=fingerprint,
                result=ConnectorResult(status=ConnectorStatus.REJECTED, error_code=exc.code, error_message=str(exc)),
            )
        except Exception as exc:
            return AutomationExecutionDocument(
                request_fingerprint=fingerprint,
                result=ConnectorResult(status=ConnectorStatus.FAILED, error_code=exc.__class__.__name__, error_message="Connector failed"),
            )
