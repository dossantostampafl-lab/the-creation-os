from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .evidence import EvidenceRecord


class FindingStatus(StrEnum):
    HYPOTHESIS = "hypothesis"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"
    NOT_REPRODUCED = "not_reproduced"
    REJECTED = "rejected"


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str


@dataclass(frozen=True)
class Finding:
    finding_id: str
    mission_id: str
    action_id: str
    task_id: str
    environment_id: str
    title: str
    attack_evidence: tuple[str, ...] = field(default_factory=tuple)
    defense_evidence: tuple[str, ...] = field(default_factory=tuple)
    status: str = FindingStatus.HYPOTHESIS.value


def verify_finding(
    attack: EvidenceRecord | None,
    defense: EvidenceRecord | None,
    *,
    purple_required: bool,
    reproduced: bool,
    mission_id: str | None = None,
    action_id: str | None = None,
    environment_id: str | None = None,
) -> VerificationResult:
    """Confirmation needs intact attack evidence, defense evidence when Purple applies, the same
    mission/action/environment across the chain, and a reproduction. Anything less stays short of it."""
    if attack is None:
        return VerificationResult(FindingStatus.HYPOTHESIS.value, "attack_evidence_missing")
    if not attack.integrity_ok():
        return VerificationResult(FindingStatus.REJECTED.value, "attack_evidence_invalid")
    for record in (attack, defense):
        if record is None:
            continue
        if not record.integrity_ok():
            return VerificationResult(FindingStatus.REJECTED.value, "evidence_invalid")
        if (mission_id and record.mission_id != mission_id) or (action_id and record.action_id != action_id):
            return VerificationResult(FindingStatus.REJECTED.value, "correlation_mismatch")
        if environment_id and record.environment_id != environment_id:
            return VerificationResult(FindingStatus.REJECTED.value, "environment_mismatch")
    if defense is not None and defense.environment_id != attack.environment_id:
        return VerificationResult(FindingStatus.REJECTED.value, "environment_mismatch")
    if purple_required and defense is None:
        return VerificationResult(FindingStatus.PROBABLE.value, "defense_evidence_required")
    if not reproduced:
        return VerificationResult(FindingStatus.NOT_REPRODUCED.value, "replay_failed")
    return VerificationResult(FindingStatus.CONFIRMED.value, "evidence_verified")
