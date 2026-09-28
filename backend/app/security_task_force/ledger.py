from __future__ import annotations

from pathlib import Path
from typing import Any

from ._state_file import load_state, save_state


class DispatchLedger:
    """At-most-once record of state-changing dispatches, keyed by idempotency key.

    A key is reserved before dispatch and completed after. A key reserved but never completed
    (a crash in between) is reported as unknown and is never dispatched again on its own."""

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

    def reserve(self, key: str) -> str:
        """'reserved' if this call now owns the dispatch; 'done' or 'unknown' if a prior call did."""
        state = self._state()
        entry = state.get(key)
        if entry is None:
            state[key] = {"status": "reserved"}
            self._write(state)
            return "reserved"
        return "done" if entry["status"] == "done" else "unknown"

    def complete(self, key: str, result: dict[str, Any]) -> None:
        state = self._state()
        state[key] = {"status": "done", "result": result}
        self._write(state)

    def result(self, key: str) -> dict[str, Any] | None:
        entry = self._state().get(key)
        return entry["result"] if entry and entry["status"] == "done" else None
