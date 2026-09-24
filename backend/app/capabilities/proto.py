from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, CapabilityResult

_ALLOWED_JOBS = frozenset({"market-data-health", "opportunity-scan", "shadow-decision"})
_ALLOWED_MODES = frozenset({"LIVE_MONITORING", "SIMULATION", "PAPER_TRADING", "HISTORICAL_REPLAY"})
_ALLOWED_PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "CRITICAL"})
_TERMINAL_STATES = frozenset({"COMPLETED", "BLOCKED", "DEGRADED"})
_TRANSPORT_OVERRIDE_KEYS = frozenset(
    {
        "base_url",
        "url",
        "endpoint",
        "token",
        "secret",
        "headers",
        "x_proto_creation_token",
    }
)


class ProtoMissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1"
    mission_id: UUID
    origin: str = "THE_CREATION"
    objective: str = Field(min_length=1, max_length=2000)
    requested_jobs: tuple[str, ...] = Field(min_length=1, max_length=32)
    execution_mode: str
    priority: str = "NORMAL"
    scope: tuple[str, ...] = Field(default=(), max_length=500)
    constraints: dict[str, Any] = Field(default_factory=dict)
    deadline: datetime | None = None

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        if value != "THE_CREATION":
            raise ValueError("PROTO mission origin must remain THE_CREATION")
        return value

    @field_validator("requested_jobs")
    @classmethod
    def validate_jobs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(job.strip() for job in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("PROTO requested_jobs must not contain duplicates")
        unsupported = sorted(set(normalized) - _ALLOWED_JOBS)
        if unsupported:
            raise ValueError("PROTO job is outside the safe Creation bridge allowlist")
        return normalized

    @field_validator("execution_mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _ALLOWED_MODES:
            raise ValueError("PROTO execution mode is outside the safe Creation bridge modes")
        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _ALLOWED_PRIORITIES:
            raise ValueError("PROTO mission priority is invalid")
        return normalized

    @model_validator(mode="after")
    def validate_deadline(self) -> ProtoMissionRequest:
        if self.deadline is not None and (
            self.deadline.tzinfo is None or self.deadline.utcoffset() is None
        ):
            raise ValueError("PROTO mission deadline must be timezone-aware")
        return self


class ProtoMissionReceipt(BaseModel):
    mission_id: UUID
    state: str
    accepted_jobs: tuple[str, ...] = ()
    rejected_reason: str | None = None
    job_run_ids: tuple[str, ...] = ()
    financial_connectivity: bool = False
    real_money_execution: bool = False

    @field_validator("accepted_jobs")
    @classmethod
    def validate_accepted_jobs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if set(value) - _ALLOWED_JOBS:
            raise ValueError("PROTO receipt contains a job outside the safe allowlist")
        return value

    @model_validator(mode="after")
    def validate_financial_boundary(self) -> ProtoMissionReceipt:
        if self.financial_connectivity or self.real_money_execution:
            raise ValueError("PROTO Creation bridge crossed the financial boundary")
        return self


class ProtoJobStatus(BaseModel):
    id: str
    job_name: str
    mode: str
    state: str
    result: Any = None
    last_error: str | None = None
    financial_connectivity: bool = False
    real_money_execution: bool = False

    @field_validator("job_name")
    @classmethod
    def validate_job_name(cls, value: str) -> str:
        if value not in _ALLOWED_JOBS:
            raise ValueError("PROTO status contains a job outside the safe allowlist")
        return value

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _ALLOWED_MODES:
            raise ValueError("PROTO status contains a mode outside the safe allowlist")
        return normalized

    @model_validator(mode="after")
    def validate_financial_boundary(self) -> ProtoJobStatus:
        if self.financial_connectivity or self.real_money_execution:
            raise ValueError("PROTO Creation bridge crossed the financial boundary")
        return self


class ProtoMissionStatus(BaseModel):
    mission_id: UUID
    state: str
    jobs: tuple[ProtoJobStatus, ...]
    financial_connectivity: bool = False
    real_money_execution: bool = False

    @model_validator(mode="after")
    def validate_financial_boundary(self) -> ProtoMissionStatus:
        if self.financial_connectivity or self.real_money_execution:
            raise ValueError("PROTO Creation bridge crossed the financial boundary")
        return self


class ProtoCapabilityAdapter:
    name = "proto"

    def __init__(
        self,
        *,
        base_url: str,
        shared_secret: str,
        timeout_seconds: float,
        mission_wait_seconds: float = 120.0,
        poll_interval_seconds: float = 1.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if mission_wait_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("PROTO mission wait and poll interval must be positive")
        self._base_url = base_url.rstrip("/")
        self._shared_secret = shared_secret
        self._timeout_seconds = timeout_seconds
        self._mission_wait_seconds = mission_wait_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._client = client

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        if intent.capability != self.name:
            raise ValueError("PROTO adapter received a different capability")
        if intent.action != "submit_mission":
            raise ValueError("PROTO adapter only supports submit_mission")
        if _TRANSPORT_OVERRIDE_KEYS.intersection(key.lower() for key in intent.arguments):
            raise ValueError("PROTO transport override arguments are forbidden")

        mission = ProtoMissionRequest.model_validate(intent.arguments)
        payload = mission.model_dump(mode="json")
        headers = self._headers()

        try:
            response = await self._request("POST", "/creation/missions", headers, payload)
            response.raise_for_status()
            receipt = ProtoMissionReceipt.model_validate(response.json())
            if receipt.mission_id != mission.mission_id:
                raise ValueError("PROTO receipt mission_id does not match request")
            if receipt.state == "ACCEPTED" and set(receipt.accepted_jobs) != set(
                mission.requested_jobs
            ):
                raise ValueError("PROTO receipt accepted_jobs does not match request")
            if receipt.state != "ACCEPTED":
                return self._receipt_result(intent, receipt)
            status = await self._wait_for_terminal_status(mission, headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RuntimeError("PROTO bridge transport failed") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"PROTO bridge returned HTTP {exc.response.status_code}") from exc
        except (ValueError, TypeError) as exc:
            message = str(exc)
            if "financial boundary" in message:
                raise RuntimeError("PROTO bridge violated financial boundary") from exc
            raise RuntimeError("PROTO bridge returned an invalid response") from exc

        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=status.state == "COMPLETED",
            data=status.model_dump(mode="json"),
            error=(
                {}
                if status.state == "COMPLETED"
                else {
                    "code": "PROTO_MISSION_NOT_COMPLETED",
                    "detail": status.state,
                }
            ),
        )

    async def _wait_for_terminal_status(
        self,
        mission: ProtoMissionRequest,
        headers: dict[str, str],
    ) -> ProtoMissionStatus:
        deadline = time.monotonic() + self._mission_wait_seconds
        path = f"/creation/missions/{mission.mission_id}"
        requested_jobs = set(mission.requested_jobs)
        while True:
            response = await self._request("GET", path, headers)
            response.raise_for_status()
            status = ProtoMissionStatus.model_validate(response.json())
            if status.mission_id != mission.mission_id:
                raise ValueError("PROTO status mission_id does not match request")
            returned_jobs = {job.job_name for job in status.jobs}
            if returned_jobs - requested_jobs:
                raise ValueError("PROTO status contains an unrequested job")
            if any(job.mode != mission.execution_mode for job in status.jobs):
                raise ValueError("PROTO status execution mode does not match request")
            if status.state in _TERMINAL_STATES:
                return status
            if time.monotonic() >= deadline:
                raise RuntimeError("PROTO mission did not reach a terminal state before timeout")
            await asyncio.sleep(self._poll_interval_seconds)

    def _receipt_result(
        self,
        intent: CapabilityIntent,
        receipt: ProtoMissionReceipt,
    ) -> CapabilityResult:
        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=False,
            data=receipt.model_dump(mode="json"),
            error={
                "code": "PROTO_MISSION_NOT_ACCEPTED",
                "detail": receipt.rejected_reason or receipt.state,
            },
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Proto-Creation-Token": self._shared_secret,
        }

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        if self._client is not None:
            return await self._client.request(method, url, json=payload, headers=headers)
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=False,
        ) as client:
            return await client.request(method, url, json=payload, headers=headers)
