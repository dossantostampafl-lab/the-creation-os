from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .canonicalize import canonical_hash

_SECRET_KEY = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|credential)", re.I)
REDACTED = "[redacted]"


def redact(value: Any) -> Any:
    """Routine evidence keeps references and hashes, never secrets or raw sensitive bodies."""
    if isinstance(value, dict):
        return {key: REDACTED if _SECRET_KEY.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _digest(*, mission_id: str, action_id: str, task_id: str, environment_id: str, source: str, kind: str,
            acquired_at: str, payload: dict[str, Any]) -> str:
    return canonical_hash({
        "mission_id": mission_id, "action_id": action_id, "task_id": task_id, "environment_id": environment_id,
        "source": source, "kind": kind, "acquired_at": acquired_at, "payload": payload,
    })


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    mission_id: str
    action_id: str
    task_id: str
    environment_id: str
    source: str
    kind: str  # attack | defense
    acquired_at: str
    payload: dict[str, Any]
    sha256: str

    @classmethod
    def build(cls, *, evidence_id: str, mission_id: str, action_id: str, environment_id: str, source: str,
              acquired_at: str, payload: dict[str, Any], task_id: str = "task", kind: str = "attack") -> "EvidenceRecord":
        clean = redact(payload)
        digest = _digest(mission_id=mission_id, action_id=action_id, task_id=task_id, environment_id=environment_id,
                         source=source, kind=kind, acquired_at=acquired_at, payload=clean)
        return cls(evidence_id, mission_id, action_id, task_id, environment_id, source, kind, acquired_at, clean, digest)

    def integrity_ok(self) -> bool:
        return self.sha256 == _digest(
            mission_id=self.mission_id, action_id=self.action_id, task_id=self.task_id,
            environment_id=self.environment_id, source=self.source, kind=self.kind,
            acquired_at=self.acquired_at, payload=self.payload,
        )

    def chronicle_payload(self) -> dict[str, Any]:
        """What goes to the Chronicle: correlation ids and the hash, not the body."""
        return {"evidence_id": self.evidence_id, "mission_id": self.mission_id, "action_id": self.action_id,
                "task_id": self.task_id, "environment_id": self.environment_id, "kind": self.kind,
                "evidence_sha256": self.sha256}
