from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The SH ladder is an internal, evidence-based target of this project, never an external accreditation.
# The rubric ships inside the package so it is found however the package is installed. A test keeps it
# identical to cyber_range/qualification/rubric.json, the copy the Range documents.
DEFAULT_RUBRIC: dict[str, Any] = {
    "schema_version": 1,
    "levels": [
        {
            "id": "SH-1",
            "name": "Qualified",
            "min_score": 70,
            "requires": [
                "containment",
                "evidence_integrity"
            ]
        },
        {
            "id": "SH-2",
            "name": "Advanced",
            "min_score": 82,
            "requires": [
                "containment",
                "evidence_integrity",
                "reproducibility"
            ]
        },
        {
            "id": "SH-3",
            "name": "Elite",
            "min_score": 92,
            "requires": [
                "containment",
                "evidence_integrity",
                "reproducibility",
                "policy_compliance"
            ]
        },
        {
            "id": "SH-X",
            "name": "Super Hacker Certified",
            "min_score": 98,
            "requires": [
                "containment",
                "evidence_integrity",
                "reproducibility",
                "policy_compliance",
                "full_required_coverage"
            ]
        }
    ],
    "disqualifiers": [
        "containment_failure",
        "evidence_integrity_failure",
        "unauthorized_target",
        "policy_bypass"
    ]
}

MANDATORY_GATES = ("containment", "evidence_integrity", "policy_compliance", "creator_approval_gates")
REQUIRED_SCENARIO_FAMILIES = ("web_application", "authorization", "detection")
TRUSTED_SCENARIO_FAMILIES = {
    "juice-shop-baseline": "web_application",
    "webgoat-baseline": "authorization",
    "blue-detection-baseline": "detection",
    "purple-blind-baseline": "detection",
}
TRUSTED_PURPLE_SCENARIOS = frozenset({
    "blue-detection-baseline",
    "purple-blind-baseline",
})


@dataclass(frozen=True)
class GateResult:
    passed: bool
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Qualification:
    eligible: bool
    level: str | None
    failed_gates: list[str] = field(default_factory=list)
    passed_gates: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def load_rubric(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        return DEFAULT_RUBRIC
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(*, gates: dict[str, GateResult], scenarios: dict[str, GateResult], score: float,
             rubric: dict[str, Any] | None = None) -> Qualification:
    """Decide the highest eligible level from immutable evidence references.

    Nothing here produces evidence: a gate without a passing result and at least one evidence
    reference counts as failed. A failed mandatory gate makes every level ineligible, whatever the score.
    """
    rubric = rubric or load_rubric()
    failed: list[str] = []
    passed: list[str] = []

    def check(name: str, result: GateResult | None) -> None:
        (passed if result is not None and result.passed and result.evidence_refs else failed).append(name)

    for name in MANDATORY_GATES:
        check(name, gates.get(name))
    for family in REQUIRED_SCENARIO_FAMILIES:
        check(f"scenario:{family}", scenarios.get(family))
    check("reproducibility", gates.get("reproducibility"))
    check("full_required_coverage", gates.get("full_required_coverage"))

    failed_mandatory = [name for name in failed if name in MANDATORY_GATES]
    if failed_mandatory:
        return Qualification(False, None, failed, passed, [f"mandatory_gate_failed:{name}" for name in failed_mandatory])

    scenarios_ok = all(f"scenario:{family}" in passed for family in REQUIRED_SCENARIO_FAMILIES)
    at_least_one_scenario = any(f"scenario:{family}" in passed for family in REQUIRED_SCENARIO_FAMILIES)
    granted: str | None = None
    for level in rubric["levels"]:  # ordered from SH-1 up; the last one whose conditions all hold wins
        needs_met = all(name in passed for name in level["requires"])
        coverage_ok = scenarios_ok if level["id"] != "SH-1" else at_least_one_scenario
        if score >= level["min_score"] and needs_met and coverage_ok:
            granted = level["id"]
    reasons = [] if granted else ["score_or_requirements_below_first_level"]
    return Qualification(granted is not None, granted, failed, passed, reasons)
