from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from pydantic.v1 import ValidationError

from app.capabilities.contracts import CapabilityIntent
from app.config import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "secret_key": "test-secret",
        "creator_bootstrap_username": "creator",
        "creator_bootstrap_password": "password",
        "database_url": "postgresql+asyncpg://postgres:postgres@localhost/test",
        "redis_url": "redis://localhost:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def _intent(**arguments: object) -> CapabilityIntent:
    payload: dict[str, object] = {
        "mission_id": "550e8400-e29b-41d4-a716-446655440000",
        "objective": "scan safe opportunities",
        "requested_jobs": ["opportunity-scan"],
        "execution_mode": "LIVE_MONITORING",
    }
    payload.update(arguments)
    return CapabilityIntent(
        capability="proto",
        action="submit_mission",
        arguments=payload,
    )


def test_proto_bridge_requires_url_and_secret() -> None:
    assert _settings().proto_bridge_configured is False
    assert _settings(proto_base_url="https://proto.example").proto_bridge_configured is False
    assert _settings(proto_creation_shared_secret="secret").proto_bridge_configured is False
    assert (
        _settings(
            proto_base_url="https://proto.example",
            proto_creation_shared_secret="   ",
        ).proto_bridge_configured
        is False
    )
    assert (
        _settings(
            proto_base_url="https://proto.example",
            proto_creation_shared_secret="secret",
        ).proto_bridge_configured
        is True
    )


def test_proto_bridge_rejects_http_in_production() -> None:
    with pytest.raises(ValidationError):
        _settings(
            app_env="production",
            proto_base_url="http://proto.example",
            proto_creation_shared_secret="secret",
        )


def test_proto_bridge_rejects_origin_with_path() -> None:
    with pytest.raises(ValidationError):
        _settings(
            proto_base_url="https://proto.example/creation",
            proto_creation_shared_secret="secret",
        )


@pytest.mark.asyncio
async def test_proto_adapter_waits_for_terminal_result_without_leaking_secret() -> None:
    from app.capabilities.proto import ProtoCapabilityAdapter

    captured: list[tuple[str, str, str | None, str]] = []
    status_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_calls
        body = request.content.decode()
        captured.append(
            (
                request.method,
                str(request.url),
                request.headers.get("X-Proto-Creation-Token"),
                body,
            )
        )
        if request.method == "POST":
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
        status_calls += 1
        state = "RUNNING" if status_calls == 1 else "COMPLETED"
        return httpx.Response(
            200,
            json={
                "mission_id": "550e8400-e29b-41d4-a716-446655440000",
                "state": state,
                "jobs": [
                    {
                        "id": "run-1",
                        "job_name": "opportunity-scan",
                        "mode": "LIVE_MONITORING",
                        "state": "RUNNING" if state == "RUNNING" else "SUCCEEDED",
                        "result": None if state == "RUNNING" else {"opportunity_count": 3},
                        "last_error": None,
                        "financial_connectivity": False,
                        "real_money_execution": False,
                    }
                ],
                "financial_connectivity": False,
                "real_money_execution": False,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = ProtoCapabilityAdapter(
        base_url="https://proto.example",
        shared_secret="super-secret",
        timeout_seconds=5,
        mission_wait_seconds=1,
        poll_interval_seconds=0.001,
        client=client,
    )

    result = await adapter.execute(_intent())
    await client.aclose()

    assert result.ok is True
    assert result.data["state"] == "COMPLETED"
    assert result.data["jobs"][0]["result"] == {"opportunity_count": 3}
    assert status_calls == 2
    assert captured[0][0] == "POST"
    assert captured[0][1] == "https://proto.example/creation/missions"
    assert captured[1][1] == (
        "https://proto.example/creation/missions/550e8400-e29b-41d4-a716-446655440000"
    )
    assert all(item[2] == "super-secret" for item in captured)
    assert all("super-secret" not in item[3] for item in captured)
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

    with pytest.raises(ValueError):
        await adapter.execute(_intent(requested_jobs=jobs, execution_mode=mode))
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

    with pytest.raises(ValueError, match="transport override"):
        await adapter.execute(
            _intent(
                base_url="https://attacker.example",
                token="attacker-token",
            )
        )
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

    with pytest.raises(RuntimeError, match="financial boundary"):
        await adapter.execute(_intent())
    await client.aclose()


@pytest.mark.asyncio
async def test_proto_adapter_rejects_unsafe_job_returned_by_status() -> None:
    from app.capabilities.proto import ProtoCapabilityAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "mission_id": "550e8400-e29b-41d4-a716-446655440000",
                    "state": "ACCEPTED",
                    "accepted_jobs": ["opportunity-scan"],
                    "job_run_ids": ["run-1"],
                    "financial_connectivity": False,
                    "real_money_execution": False,
                },
            )
        return httpx.Response(
            200,
            json={
                "mission_id": "550e8400-e29b-41d4-a716-446655440000",
                "state": "COMPLETED",
                "jobs": [
                    {
                        "id": "run-1",
                        "job_name": "execute-order",
                        "mode": "LIVE",
                        "state": "SUCCEEDED",
                        "result": {},
                        "financial_connectivity": False,
                        "real_money_execution": False,
                    }
                ],
                "financial_connectivity": False,
                "real_money_execution": False,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ProtoCapabilityAdapter(
        base_url="https://proto.example",
        shared_secret="secret",
        timeout_seconds=5,
        poll_interval_seconds=0.001,
        client=client,
    )

    with pytest.raises(RuntimeError, match="invalid response"):
        await adapter.execute(_intent())
    await client.aclose()


def test_worker_registers_proto_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import worker

    disabled = _settings()
    monkeypatch.setattr(worker, "settings", disabled)
    gateway = worker.build_capability_gateway()
    assert "proto" not in gateway._adapters

    enabled = _settings(
        proto_base_url="https://proto.example",
        proto_creation_shared_secret="secret",
    )
    monkeypatch.setattr(worker, "settings", enabled)
    gateway = worker.build_capability_gateway()
    assert "proto" in gateway._adapters
