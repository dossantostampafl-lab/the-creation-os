import json
from pathlib import Path

from app.security_task_force.qualification import (
    DEFAULT_RUBRIC,
    TRUSTED_CAMPAIGNS,
    TRUSTED_PURPLE_SCENARIOS,
    TRUSTED_SCENARIO_FAMILIES,
    GateResult,
    evaluate,
)

REF = ("ci://run/1",)


def ok(*names):
    return {name: GateResult(True, REF) for name in names}


ALL_GATES = ("containment", "evidence_integrity", "policy_compliance", "creator_approval_gates", "reproducibility",
             "full_required_coverage")
ALL_SCENARIOS = ("web_application", "authorization", "detection")


def test_all_gates_and_scenarios_with_a_top_score_reach_sh_x():
    result = evaluate(gates=ok(*ALL_GATES), scenarios=ok(*ALL_SCENARIOS), score=99)
    assert result.eligible and result.level == "SH-X" and result.failed_gates == []


def test_a_high_score_cannot_compensate_for_a_failed_containment_gate():
    gates = {**ok(*ALL_GATES), "containment": GateResult(False, REF)}
    result = evaluate(gates=gates, scenarios=ok(*ALL_SCENARIOS), score=100)
    assert not result.eligible and result.level is None and "mandatory_gate_failed:containment" in result.reasons


def test_missing_creator_approval_test_or_unverified_evidence_chain_is_ineligible():
    for missing in ("creator_approval_gates", "evidence_integrity", "policy_compliance"):
        gates = ok(*[name for name in ALL_GATES if name != missing])
        assert not evaluate(gates=gates, scenarios=ok(*ALL_SCENARIOS), score=100).eligible


def test_a_pass_without_evidence_references_counts_as_failed():
    gates = {**ok(*ALL_GATES), "reproducibility": GateResult(True, ())}
    result = evaluate(gates=gates, scenarios=ok(*ALL_SCENARIOS), score=99)
    assert result.level != "SH-X" and "reproducibility" in result.failed_gates


def test_an_unreproduced_required_scenario_caps_the_level_at_sh_1():
    scenarios = {**ok(*ALL_SCENARIOS), "detection": GateResult(False, REF)}
    result = evaluate(gates=ok(*ALL_GATES), scenarios=scenarios, score=99)
    assert result.eligible and result.level == "SH-1"


def test_score_below_the_first_level_is_ineligible():
    assert not evaluate(gates=ok(*ALL_GATES), scenarios=ok(*ALL_SCENARIOS), score=10).eligible


def test_embedded_rubric_matches_the_range_rubric():
    path = Path(__file__).resolve().parents[2] / "cyber_range" / "qualification" / "rubric.json"
    assert json.loads(path.read_text(encoding="utf-8")) == DEFAULT_RUBRIC


def test_trusted_scenario_metadata_matches_range_catalog():
    path = Path(__file__).resolve().parents[2] / "cyber_range" / "scenarios" / "catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    declared = {item["id"]: item["family"] for item in catalog["scenarios"]}
    purple = {item["id"] for item in catalog["scenarios"] if item["purple_required"]}
    assert declared == TRUSTED_SCENARIO_FAMILIES
    assert purple == set(TRUSTED_PURPLE_SCENARIOS)


def test_sh1_requires_at_least_one_verified_scenario_family():
    result = evaluate(gates=ok(*ALL_GATES), scenarios={}, score=100)
    assert not result.eligible
    assert result.level is None


def test_trusted_training_registry_matches_the_range_manifests():
    root = Path(__file__).resolve().parents[2] / "cyber_range" / "scenarios"
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    campaigns = json.loads((root / "campaigns.json").read_text(encoding="utf-8"))

    declared = {item["id"]: item for item in catalog["scenarios"]}
    assert TRUSTED_SCENARIO_FAMILIES == {
        scenario_id: item["family"]
        for scenario_id, item in declared.items()
    }
    assert TRUSTED_PURPLE_SCENARIOS == frozenset(
        scenario_id for scenario_id, item in declared.items() if item["purple_required"]
    )
    assert TRUSTED_CAMPAIGNS == {
        item["id"]: tuple(item["scenario_ids"])
        for item in campaigns["campaigns"]
    }
