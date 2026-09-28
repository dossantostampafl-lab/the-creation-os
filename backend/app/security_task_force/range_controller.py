from __future__ import annotations

import re
from typing import Any

import httpx

from .contracts import is_environment_id

RANGE_PREFIX = "cyber_range:"
_SCENARIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class RangeRefused(ValueError):
    """The Range only acts inside cyber_range:* environments; it never grants real authority."""


def _require_range(environment_id: str) -> None:
    if not is_environment_id(environment_id) or not environment_id.startswith(RANGE_PREFIX):
        raise RangeRefused("the Cyber Range refuses any environment that is not cyber_range:*")


def _scenario(scenario_id: str) -> str:
    if not _SCENARIO_ID.fullmatch(scenario_id) or ".." in scenario_id:
        raise RangeRefused("scenario id is not allowed")
    return scenario_id


class RangeController:
    """Lifecycle client for the Range controller API (cyber_range/controller)."""

    def __init__(self, base_url: str = "http://127.0.0.1:7070", *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=10.0) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

    async def scenarios(self) -> list[dict[str, Any]]:
        return (await self._call("GET", "/scenarios"))["scenarios"]

    async def start(self, environment_id: str, scenario_id: str) -> dict[str, Any]:
        _require_range(environment_id)
        return await self._call("POST", f"/scenarios/{_scenario(scenario_id)}/start")

    async def reset(self, environment_id: str) -> dict[str, Any]:
        _require_range(environment_id)
        return await self._call("POST", "/reset")

    async def stop(self, environment_id: str) -> dict[str, Any]:
        """Stopping clears Range state, so nothing stays active for a finished mission."""
        return await self.reset(environment_id)

    async def verify(self, environment_id: str, scenario_id: str) -> bool:
        _require_range(environment_id)
        _scenario(scenario_id)
        state = await self._call("GET", "/state")
        return any(s.get("scenario_id") == scenario_id and s.get("status") == "active" for s in state["scenarios"])

    async def record_evidence(self, environment_id: str, scenario_id: str, kind: str, payload: dict[str, Any]) -> str:
        _require_range(environment_id)
        _scenario(scenario_id)
        result = await self._call("POST", "/evidence", json={"scenario_id": scenario_id, "kind": kind, "payload": payload})
        return result["evidence_id"]
