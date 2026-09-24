from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.domain import Actor

from .contracts import MissionContract


@dataclass(frozen=True)
class MissionStatusView:
    mission_id: str
    status: str


class SecurityTaskForceAdapter:
    """Explicit boundary. Does not expose repositories, gateway handles or sandbox handles."""

    async def compile_intent(self, creator: Actor, intent: str, context: dict[str, Any]) -> MissionContract:
        raise NotImplementedError("Mission Compiler must supply a schema-valid contract")

    async def get_mission_status(self, creator: Actor, mission_id: str) -> MissionStatusView:
        raise NotImplementedError

    async def submit_creator_approval(self, creator: Actor, action_id: str, decision: str) -> str:
        if decision not in {"approve", "deny"}:
            raise ValueError("invalid creator decision")
        return f"creator-approval:{creator.id}:{action_id}:{decision}"

    async def cancel_mission(self, creator: Actor, mission_id: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("cancellation reason is required")
