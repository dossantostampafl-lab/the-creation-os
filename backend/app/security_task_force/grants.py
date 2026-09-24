from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CapabilityGrant:
    grant_id: str
    mission_id: str
    mission_version: int
    actor: str
    capability: str
    target_id: str
    environment: str
    action_class: str
    expires_at: datetime
    max_invocations: int
    revoked: bool = False

    def permits(
        self,
        *,
        mission_id: str,
        mission_version: int,
        actor: str,
        capability: str,
        target_id: str,
        environment: str,
        action_class: str,
        invocations: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        return (
            not self.revoked
            and self.expires_at > now
            and self.mission_id == mission_id
            and self.mission_version == mission_version
            and self.actor == actor
            and self.capability == capability
            and self.target_id == target_id
            and self.environment == environment
            and self.action_class == action_class
            and invocations < self.max_invocations
        )
