from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from app.capabilities.contracts import CapabilityIntent, CapabilityResult

_ALLOWED_JOBS = frozenset({"market-data-health", "opportunity-scan", "shadow-decision"})
_ALLOWED_MODES = frozenset({"LIVE_MONITORING", "SIMULATION", "PAPER_TRADING", "HISTORICAL_REPLAY"})
_ALLOWED_PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "CRITICAL"})
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

    @model_validator(mode="after")
    def validate_financial_boundary(self) -> ProtoMissionReceipt:
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
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._shared_secret = shared_secret
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def execute(self, intent: CapabilityIntent) -> CapabilityResult:
        if intent.capability != self.name:
            raise ValueError("PROTO adapter received a different capability")
        if intent.action != "submit_mission":
            raise ValueError("PROTO adapter only supports submit_mission")
        if _TRANSPORT_OVERRIDE_KEYS.intersection(key.lower() for key in intent.arguments):
            raise ValueError("PROTO transport override arguments are forbidden")

        mission = ProtoMissionRequest.model_validate(intent.arguments)
        payload = mission.model_dump(mode="json")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Proto-Creation-Token": self._shared_secret,
        }

        try:
            response = await self._post(payload, headers)
            response.raise_for_status()
            receipt = ProtoMissionReceipt.model_validate(response.json())
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RuntimeError("PROTO bridge transport failed") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"PROTO bridge returned HTTP {exc.response.status_code}") from exc
        except (ValueError, TypeError) as exc:
            message = str(exc)
            if "financial boundary" in message:
                raise RuntimeError("PROTO bridge violated financial boundary") from exc
            raise RuntimeError("PROTO bridge returned an invalid response") from exc

        data = receipt.model_dump(mode="json")
        return CapabilityResult(
            capability=self.name,
            action=intent.action,
            ok=receipt.state == "ACCEPTED",
            data=data,
            error=(
                {}
                if receipt.state == "ACCEPTED"
                else {
                    "code": "PROTO_MISSION_NOT_ACCEPTED",
                    "detail": receipt.rejected_reason or receipt.state,
                }
            ),
        )

    async def _post(self, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        url = f"{self._base_url}/creation/missions"
        if self._client is not None:
            return await self._client.post(url, json=payload, headers=headers)
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=False,
        ) as client:
            return await client.post(url, json=payload, headers=headers)
