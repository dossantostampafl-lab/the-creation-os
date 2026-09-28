from __future__ import annotations

from typing import Any, Protocol

import httpx

from .contracts import ActionRequest, MissionContract


class PolicyUnavailable(RuntimeError):
    """The policy engine could not give an answer. Callers must treat it as a denial."""


class PolicyClient(Protocol):
    async def evaluate(self, contract: MissionContract, action: ActionRequest, approval: str | None) -> tuple[bool, list[str]]:
        """(permitted, reason codes) from the external policy engine."""


def policy_input(contract: MissionContract, action: ActionRequest, approval: str | None) -> dict[str, Any]:
    return {
        "mission": contract.normalized_payload(),
        "mission_id": action.mission_id,
        "mission_version": action.mission_version,
        "target_id": action.target_id,
        "environment_id": action.environment_id,
        "action_class": action.action_class,
        "risk_class": action.risk_class.value,
        "creator_approval_reference": approval,
    }


class OpaClient:
    def __init__(self, base_url: str, *, timeout: float = 2.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/data/creation/stf/decision"
        self._timeout = timeout
        self._transport = transport

    async def evaluate(self, contract: MissionContract, action: ActionRequest, approval: str | None) -> tuple[bool, list[str]]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(self._url, json={"input": policy_input(contract, action, approval)})
                response.raise_for_status()
                result = response.json().get("result")
        except (httpx.HTTPError, ValueError) as error:
            raise PolicyUnavailable(error.__class__.__name__) from error
        if not isinstance(result, dict) or not isinstance(result.get("allow"), bool):
            raise PolicyUnavailable("malformed policy answer")
        return result["allow"], [str(item) for item in result.get("reasons", [])]
