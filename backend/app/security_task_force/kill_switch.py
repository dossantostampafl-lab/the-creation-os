from __future__ import annotations

from pathlib import Path

from ._state_file import StateUnreadable, load_state, save_state


class KillSwitch:
    """Global and per-Mission stop for new dispatch. Persistent when given a path.

    With a path the state is re-read on every check, so engaging it in one process stops the others,
    and an unreadable file blocks dispatch instead of allowing it.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._global = False
        self._missions: set[str] = set()

    def _load(self) -> tuple[bool, set[str]]:
        if self._path is None:
            return self._global, self._missions
        state = load_state(self._path)
        return bool(state.get("global")), set(state.get("missions", []))

    def _store(self, global_killed: bool, missions: set[str]) -> None:
        self._global, self._missions = global_killed, missions
        save_state(self._path, {"global": global_killed, "missions": sorted(missions)})

    @property
    def global_killed(self) -> bool:
        return self._load()[0]

    def kill_global(self) -> None:
        self._store(True, self._load()[1])

    def kill_mission(self, mission_id: str) -> None:
        global_killed, missions = self._load()
        self._store(global_killed, missions | {mission_id})

    def release_mission(self, mission_id: str) -> None:
        global_killed, missions = self._load()
        self._store(global_killed, missions - {mission_id})

    def dispatch_allowed(self, mission_id: str) -> bool:
        try:
            global_killed, missions = self._load()
        except StateUnreadable:
            return False
        return not global_killed and mission_id not in missions
