from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from pydantic.v1 import ValidationError

from app.capabilities.contracts import CapabilityIntent
from app.config import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "APP_SECRET_KEY": "test-secret",
        "CREATOR_BOOTSTRAP_USERNAME": "creator",
        "CREATOR_BOOTSTRAP_PASSWORD": "password",
        "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost/test",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def test_proto_bridge_requires_url_and_secret() -> None:
    assert _settings().proto_bridge_configured is False
    assert _settings(PROTO_BASE_URL="https://proto.example").proto_bridge_configured is False
    assert _settings(PROTO_CREATION_SHARED_SECRET="secret").proto_bridge_configured is False
    assert (
        _settings(
            PROTO_BASE_URL="https://proto.example",
            PROTO_CREATION_SHARED_SECRET="secret",
        ).proto_bridge_configured
        is True
    )


def test_proto_bridge_rejects_http_in_production() -> None:
    with pytest.raises(ValidationError):
        _settings(
            APP_ENV="production",
            PROTO_BASE_URL="http://proto.example",
            PROTO_CREATION_SHARED_SECRET="secret",
        )


@pytest.mark.asyncio
async def test_proto_adapter_submits_safe_mission_without_leaking_secret() -> None:
    from app.capabilities.proto import ProtoCapabilityAdapter

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-Proto-Creation-Token")
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "mission_id": "550e8400-e29b-41d4-a716-446655440000",
                "state": "ACCEPTED",
                "accepted_jobs": ["opportunity-scan"],
                "rejected_reason": None,
                "job_run_ids": ["run-1"],
                "financial_connectivity": False,
                "real_money_execution": False,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = ProtoCapabilityAdapter(
        base_url="https://proto.example",
        shared_secret="super-secret",
        timeout_seconds=5,
        client=client,
    )
    intent = CapabilityIntent(
        capability="proto",
        action="submit_mission",
        arguments={
            "mission_id": "550e8400-e29b-41d4-a716-446655440000",
            "objective": "scan safe opportunities",
            "requested_jobs": ["opportunity-scan"],
            "execution_mode": "LIVE_MONITORING",
        },
    )

    result = await adapter.execute(intent)
    await client.aclose()

    assert result.ok is True
    assert captured["url"] == "https://proto.example/creation/missions"
    assert captured["token"] == "super-secret"
    assert "super-secret" not in str(result.model_dump(mode="json"))
    assert result.data["financial_connectivity"] is False
    assert result.data["real_money_execution"] is False
    UUID(result.data["mission_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("jobs", "mode"),
    [
        (["execute-order"], "LIVE_MONITORING"),
        (["opportunity-scan"], "LIVE"),
        (["opportunity-scan"], "LIVE_CANARY"),
    ],
)
async def test_proto_adapter_rejects_unsafe_jobs_and_modes(jobs: list[str], mode: str) -> None:
    from app.capabilities.proto import ProtoCapabilityAdapter

    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ProtoCapabilityAdapter(
        base_url="https://proto.example",
        shared_secret="secret",
        timeout_seconds=5,
        client=client,
    )
    intent = CapabilityIntent(
        capability="proto",
        action="submit_mission",
        arguments={
            "mission_id": "550e8400-e29b-41d4-a716-446655440000",
            "objective": "unsafe attempt",
            "requested_jobs": jobs,
            "execution_mode": mode,
        },
    )

    with pytest.raises(ValueError):
        await adapter.execute(intent)
    await client.aclose()
    assert called is False


@pytest.mark.asyncio
async def test_proto_adapter_rejects_transport_override_arguments() -> None:
    from app.capabilities.proto import ProtoCapabilityAdapter

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    adapter = ProtoCapabilityAdapter(
        base_url="https://proto.example",
        shared_secret="secret",
        timeout_seconds=5,
        client=client,
    )
    intent = CapabilityIntent(
        capability="proto",
        action="submit_mission",
        arguments={
            "mission_id": "550e8400-e29b-41d4-a716-446655440000",
            "objective": "override attempt",
            "requested_jobs": ["opportunity-scan"],
            "execution_mode": "LIVE_MONITORING",
            "base_url": "https://attacker.example",
            "token": "attacker-token",
        },
    )

    with pytest.raises(ValueError, match="transport override"):
        await adapter.execute(intent)
    await client.aclose()


@pytest.mark.asyncio
async def test_proto_adapter_rejects_financial_invariant_violation() -> None:
    from app.capabilities.proto import ProtoCapabilityAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "mission_id": "550e8400-e29b-41d4-a716-446655440000",
                "state": "ACCEPTED",
                "accepted_jobs": ["opportunity-scan"],
                "job_run_ids": ["run-1"],
                "financial_connectivity": True,
                "real_money_execution": False,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ProtoCapabilityAdapter(
        base_url="https://proto.example",
        shared_secret="secret",
        timeout_seconds=5,
        client=client,
    )
    intent = CapabilityIntent(
        capability="proto",
        action="submit_mission",
        arguments={
            "mission_id": "550e8400-e29b-41d4-a716-446655440000",
            "objective": "scan",
            "requested_jobs": ["opportunity-scan"],
            "execution_mode": "LIVE_MONITORING",
        },
    )

    with pytest.raises(RuntimeError, match="financial boundary"):
        await adapter.execute(intent)
    await client.aclose()


def test_worker_registers_proto_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import worker

    disabled = _settings()
    monkeypatch.setattr(worker, "settings", disabled)
    gateway = worker.build_capability_gateway()
    assert "proto" not in gateway._adapters

    enabled = _settings(
        PROTO_BASE_URL="https://proto.example",
        PROTO_CREATION_SHARED_SECRET="secret",
    )
    monkeypatch.setattr(worker, "settings", enabled)
    gateway = worker.build_capability_gateway()
    assert "proto" in gateway._adapters
