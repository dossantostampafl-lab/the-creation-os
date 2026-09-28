from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._state_file import StateUnreadable, load_state, save_state
from .contracts import MissionContract
from .mission_compiler import CompilationResult, verify_compiled


class ContractStore:
    """Persisted compiled contracts, re-verified from their hash every time they are read.

    A record whose hash no longer matches its content, or a file that cannot be read, yields no
    contract: the Authorization Plane then denies with mission_unknown instead of trusting it."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._memory: dict[str, Any] = {}

    def _state(self) -> dict[str, Any]:
        return load_state(self._path) if self._path is not None else self._memory

    def put(self, result: CompilationResult) -> str:
        record = result.record()
        state = self._state()
        state[record["contract"]["mission_id"]] = record
        if self._path is not None:
            save_state(self._path, state)
        else:
            self._memory = state
        return record["contract_hash"]

    def record(self, mission_id: str) -> Mapping[str, Any] | None:
        try:
            return self._state().get(mission_id)
        except StateUnreadable:
            return None

    def get(self, mission_id: str) -> MissionContract | None:
        record = self.record(mission_id)
        if record is None or not verify_compiled(record):
            return None
        return MissionContract.model_validate(record["contract"])
