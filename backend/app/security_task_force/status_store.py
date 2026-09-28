from __future__ import annotations

from pathlib import Path
from typing import Any

from ._state_file import StateUnreadable, load_state, save_state


class MissionStatusStore:
    """Mission state and verified findings as the Creator sees them. Persistent when given a path."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._memory: dict[str, Any] = {}

    def _state(self) -> dict[str, Any]:
        return load_state(self._path) if self._path is not None else self._memory

    def _write(self, state: dict[str, Any]) -> None:
        if self._path is not None:
            save_state(self._path, state)
        else:
            self._memory = state

    def set_state(self, mission_id: str, state: str) -> None:
        data = self._state()
        entry = data.setdefault(mission_id, {"state": state, "findings": []})
        entry["state"] = state
        self._write(data)

    def state(self, mission_id: str) -> str | None:
        try:
            entry = self._state().get(mission_id)
        except StateUnreadable:
            return None
        return entry["state"] if entry else None

    def add_finding(self, mission_id: str, finding: dict[str, Any]) -> None:
        data = self._state()
        entry = data.setdefault(mission_id, {"state": "RUNNING", "findings": []})
        entry["findings"].append(finding)
        self._write(data)

    def findings(self, mission_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
        try:
            entry = self._state().get(mission_id)
        except StateUnreadable:
            return []
        items = list(entry["findings"]) if entry else []
        return [item for item in items if status is None or item.get("status") == status]
