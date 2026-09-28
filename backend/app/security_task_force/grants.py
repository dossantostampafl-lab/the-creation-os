from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from ._state_file import StateUnreadable, load_state, save_state
from .contracts import ActionRequest, CapabilityGrant

DEFAULT_TTL = timedelta(minutes=5)
MAX_TTL = timedelta(minutes=30)

__all__ = ["CapabilityGrant", "GrantStore", "DEFAULT_TTL", "MAX_TTL"]


class GrantStore:
    """Issues, revokes and counts grants. With a path it survives a restart; without, it is memory.

    Revocation and invocation counts live beside the grants and are re-read on every check when a
    path is set, so a revoke made by one process is seen by all of them. A state file that cannot be
    read makes every check fail: authority is never assumed.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._memory: dict = {"grants": {}, "invocations": {}, "revoked_missions": {}}
        if path is not None:
            self._memory = self._read()

    def _read(self) -> dict:
        state = load_state(self._path)
        state.setdefault("grants", {})
        state.setdefault("invocations", {})
        state.setdefault("revoked_missions", {})
        return state

    def _state(self) -> dict:
        return self._read() if self._path is not None else self._memory

    def _write(self, state: dict) -> None:
        if self._path is not None:
            save_state(self._path, state)
        else:
            self._memory = state

    def issue(self, action: ActionRequest, *, ttl: timedelta = DEFAULT_TTL, not_after: datetime | None = None,
              max_invocations: int = 1, now: datetime | None = None) -> CapabilityGrant:
        moment = now or datetime.now(timezone.utc)
        expires = moment + min(ttl, MAX_TTL)
        if not_after is not None:
            expires = min(expires, not_after)
        grant = CapabilityGrant(
            grant_id=f"grant:{uuid4()}", mission_id=action.mission_id, mission_version=action.mission_version,
            actor=action.actor, capability=action.capability, target_id=action.target_id,
            environment_id=action.environment_id, action_class=action.action_class,
            expires_at=expires, max_invocations=max_invocations,
        )
        state = self._state()
        state["grants"][grant.grant_id] = grant.model_dump(mode="json")
        self._write(state)
        return grant

    def get(self, grant_id: str) -> CapabilityGrant | None:
        raw = self._state()["grants"].get(grant_id)
        return CapabilityGrant.model_validate(raw) if raw else None

    def revoke(self, grant_id: str) -> bool:
        state = self._state()
        if grant_id not in state["grants"]:
            return False
        state["grants"][grant_id]["revoked"] = True
        self._write(state)
        return True

    def revoke_mission(self, mission_id: str, *, below_version: int | None = None) -> int:
        """Revoke every grant of a Mission and remember it, so a grant issued later is refused too."""
        state = self._state()
        count = 0
        for raw in state["grants"].values():
            if raw["mission_id"] == mission_id and not raw["revoked"]:
                raw["revoked"] = True
                count += 1
        state["revoked_missions"][mission_id] = below_version if below_version is not None else 10**9
        self._write(state)
        return count

    def invocations(self, grant_id: str) -> int:
        return int(self._state()["invocations"].get(grant_id, 0))

    def allows(self, grant_id: str, action: ActionRequest, *, now: datetime | None = None) -> bool:
        try:
            state = self._state()
        except StateUnreadable:
            return False
        raw = state["grants"].get(grant_id)
        if not raw:
            return False
        cutoff = state["revoked_missions"].get(action.mission_id)
        if cutoff is not None and action.mission_version <= cutoff:
            return False
        grant = CapabilityGrant.model_validate(raw)
        return grant.matches(action, invocations=int(state["invocations"].get(grant_id, 0)), now=now)

    def consume(self, grant_id: str, action: ActionRequest, *, now: datetime | None = None) -> bool:
        """Spend one invocation atomically with the check; False means the grant did not allow it."""
        if not self.allows(grant_id, action, now=now):
            return False
        state = self._state()
        state["invocations"][grant_id] = int(state["invocations"].get(grant_id, 0)) + 1
        self._write(state)
        return True
