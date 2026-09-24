from __future__ import annotations

from dataclasses import dataclass

from .evidence import EvidenceRecord


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str


def verify_finding(attack: EvidenceRecord | None, defense: EvidenceRecord | None, *, purple_required: bool, reproduced: bool) -> VerificationResult:
    if attack is None or not attack.integrity_ok():
        return VerificationResult("rejected", "attack_evidence_missing_or_invalid")
    if purple_required and (defense is None or not defense.integrity_ok()):
        return VerificationResult("probable", "defense_evidence_required")
    if not reproduced:
        return VerificationResult("not_reproduced", "replay_failed")
    return VerificationResult("confirmed", "evidence_verified")
