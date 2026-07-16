from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.automation.connectors.rest import RestrictedRestConnector
from app.automation.contracts import ConnectorCapability, ConnectorRequest, ConnectorResult, ConnectorStatus
from app.automation.executor import AutomationExecutor, request_fingerprint
from app.automation.registry import ConnectorRegistry
from app.core.domain import Actor
from app.models.automation import AutomationExecution
from app.services.automation import AutomationIdempotencyConflict, AutomationService


class EchoConnector:
    connector_id = "echo"

    def capabilities(self) -> list[ConnectorCapability]:
        return [ConnectorCapability(name="echo", description="Echo payload", input_schema={})]

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED, output={"payload": request.payload})


class SlowConnector(EchoConnector):
    connector_id = "slow"

    async def execute(self, request: ConnectorRequest) -> ConnectorResult:
        await asyncio.sleep(0.2)
        return ConnectorResult(status=ConnectorStatus.SUCCEEDED)


class FakeAutomationRepository:
    def __init__(self) -> None:
        self.item: AutomationExecution | None = None
        self.events: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    async def execution(self, creator_id: str, connector_id: str, idempotency_key: str) -> AutomationExecution | None:
        if self.item and self.item.creator_id == creator_id and self.item.connector_id == connector_id and self.item.idempotency_key == idempotency_key:
            return self.item
        return None

    async def add(self, item: AutomationExecution) -> AutomationExecution:
        item.id = "execution-1"
        self.item = item
        return item

    async def add_event(self, aggregate_id: str, actor_id: str, actor_role: str, correlation_id: str, payload: dict) -> None:
        self.events.append(payload)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def connector_request(**overrides) -> ConnectorRequest:
    payload: dict[str, Any] = {
        "connector_id": "echo",
        "capability": "echo",
        "payload": {"message": "hello"},
        "timeout_seconds": 1.0,
        "idempotency_key": "same-key",
        "correlation_id": "correlation-1",
    }
    payload.update(overrides)
    return ConnectorRequest(**payload)


def test_request_fingerprint_is_deterministic_and_payload_sensitive():
    first = request_fingerprint(connector_request(payload={"a": 1, "b": 2}))
    second = request_fingerprint(connector_request(payload={"b": 2, "a": 1}))
    changed = request_fingerprint(connector_request(payload={"a": 1}))

    assert first == second
    assert first != changed
    assert len(first) == 64


@pytest.mark.asyncio
async def test_executor_validates_capability_and_times_out():
    registry = ConnectorRegistry()
    registry.register(EchoConnector())
    registry.register(SlowConnector())

    success = await AutomationExecutor(registry).execute(connector_request())
    timeout = await AutomationExecutor(registry).execute(
        connector_request(connector_id="slow", capability="echo", timeout_seconds=0.01)
    )
    rejected = await AutomationExecutor(registry).execute(connector_request(capability="missing"))

    assert success.result.status == ConnectorStatus.SUCCEEDED
    assert timeout.result.status == ConnectorStatus.TIMEOUT
    assert rejected.result.status == ConnectorStatus.REJECTED


@pytest.mark.asyncio
async def test_restricted_rest_connector_allows_only_safe_preapproved_requests():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") is None
        return httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json", "set-cookie": "secret"})

    connector = RestrictedRestConnector(
        allowed_hosts={"example.com"},
        allowed_methods={"GET"},
        max_response_bytes=64,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    connector._reject_private_host = AsyncNoop()  # type: ignore[method-assign]

    result = await connector.execute(
        connector_request(
            connector_id="restricted_rest",
            capability="http_request",
            payload={"method": "GET", "url": "https://example.com/data?token=secret", "headers": {"Accept": "application/json"}},
        )
    )

    assert result.status == ConnectorStatus.SUCCEEDED
    assert result.output["url"] == "https://example.com/data"
    assert "set-cookie" not in result.output["headers"]
    await connector._client.aclose()  # type: ignore[union-attr]


class AsyncNoop:
    async def __call__(self, host: str) -> None:
        return None


@pytest.mark.asyncio
async def test_restricted_rest_connector_blocks_localhost_and_sensitive_headers():
    connector = RestrictedRestConnector(allowed_hosts={"127.0.0.1"}, allowed_methods={"GET"}, max_response_bytes=64)

    with pytest.raises(Exception, match="blocked network"):
        await connector.execute(
            connector_request(
                connector_id="restricted_rest",
                capability="http_request",
                payload={"method": "GET", "url": "http://127.0.0.1/status"},
            )
        )

    connector = RestrictedRestConnector(allowed_hosts={"example.com"}, allowed_methods={"GET"}, max_response_bytes=64)
    connector._reject_private_host = AsyncNoop()  # type: ignore[method-assign]
    with pytest.raises(Exception, match="header is not allowed"):
        await connector.execute(
            connector_request(
                connector_id="restricted_rest",
                capability="http_request",
                payload={"method": "GET", "url": "https://example.com", "headers": {"Authorization": "secret"}},
            )
        )


@pytest.mark.asyncio
async def test_automation_service_is_idempotent_and_audited():
    registry = ConnectorRegistry()
    registry.register(EchoConnector())
    repository = FakeAutomationRepository()
    service = AutomationService(repository, registry)  # type: ignore[arg-type]
    actor = Actor(id="creator-1", role="creator")

    first, created = await service.execute(
        actor,
        connector_id="echo",
        capability="echo",
        payload={"message": "hello"},
        timeout_seconds=1,
        idempotency_key="same-key",
        correlation_id="correlation-1",
    )
    second, replay_created = await service.execute(
        actor,
        connector_id="echo",
        capability="echo",
        payload={"message": "hello"},
        timeout_seconds=1,
        idempotency_key="same-key",
        correlation_id="correlation-2",
    )

    assert created is True
    assert replay_created is False
    assert second.request_fingerprint == first.request_fingerprint
    assert len(repository.events) == 1
    assert repository.events[0]["status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_automation_service_rejects_idempotency_conflict_without_new_event():
    registry = ConnectorRegistry()
    registry.register(EchoConnector())
    repository = FakeAutomationRepository()
    service = AutomationService(repository, registry)  # type: ignore[arg-type]
    actor = Actor(id="creator-1", role="creator")

    await service.execute(
        actor,
        connector_id="echo",
        capability="echo",
        payload={"message": "hello"},
        timeout_seconds=1,
        idempotency_key="same-key",
        correlation_id="correlation-1",
    )

    with pytest.raises(AutomationIdempotencyConflict):
        await service.execute(
            actor,
            connector_id="echo",
            capability="echo",
            payload={"message": "changed"},
            timeout_seconds=1,
            idempotency_key="same-key",
            correlation_id="correlation-2",
        )

    assert len(repository.events) == 1
