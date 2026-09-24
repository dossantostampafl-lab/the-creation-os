from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    mission_id: str
    action_id: str
    source: str
    acquired_at: str
    payload: dict[str, Any]
    sha256: str

    @classmethod
    def build(
        cls,
        *,
        evidence_id: str,
        mission_id: str,
        action_id: str,
        source: str,
        acquired_at: str,
        payload: dict[str, Any],
    ) -> "EvidenceRecord":
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        return cls(
            evidence_id,
            mission_id,
            action_id,
            source,
            acquired_at,
            payload,
            digest,
        )

    def integrity_ok(self) -> bool:
        encoded = json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest() == self.sha256
