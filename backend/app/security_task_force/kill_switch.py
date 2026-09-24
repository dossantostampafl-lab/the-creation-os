from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KillSwitch:
    global_killed: bool = False
    killed_missions: set[str] | None = None

    def __post_init__(self) -> None:
        if self.killed_missions is None:
            self.killed_missions = set()

    def kill_global(self) -> None:
        self.global_killed = True

    def kill_mission(self, mission_id: str) -> None:
        assert self.killed_missions is not None
        self.killed_missions.add(mission_id)

    def dispatch_allowed(self, mission_id: str) -> bool:
        assert self.killed_missions is not None
        return not self.global_killed and mission_id not in self.killed_missions
