package creation.stf_test

import rego.v1

import data.creation.stf

base_mission := {
	"mission_id": "m1",
	"mission_version": 1,
	"authorized_environments": ["cyber_range:lab-a"],
	"authorized_targets": ["juice-shop"],
	"excluded_targets": [],
	"allowed_action_classes": ["validate"],
	"risk_ceiling": "R4",
	"time_window": {"start": "2000-01-01T00:00:00Z", "end": "2999-01-01T00:00:00Z"},
}

base_input := {
	"mission": base_mission,
	"mission_id": "m1",
	"mission_version": 1,
	"target_id": "juice-shop",
	"environment_id": "cyber_range:lab-a",
	"action_class": "validate",
	"risk_class": "R2",
	"creator_approval_reference": null,
}

test_default_deny_without_input if {
	not stf.allow with input as {}
}

test_partial_input_is_denied if {
	not stf.allow with input as {"risk_class": "R0"}
	not stf.allow with input as {"mission": base_mission}
	not stf.allow with input as object.remove(base_input, ["mission_version"])
}

test_in_scope_action_is_allowed if {
	stf.allow with input as base_input
}

test_wrong_environment_is_denied if {
	i := object.union(base_input, {"environment_id": "real:prod-a"})
	not stf.allow with input as i
	"environment_not_authorized" in stf.deny_reasons with input as i
}

test_wrong_or_excluded_target_is_denied if {
	i := object.union(base_input, {"target_id": "other"})
	"target_not_authorized" in stf.deny_reasons with input as i
	m := object.union(base_mission, {"excluded_targets": ["juice-shop"]})
	"target_not_authorized" in stf.deny_reasons with input as object.union(base_input, {"mission": m})
}

test_stale_mission_version_is_denied if {
	i := object.union(base_input, {"mission_version": 2})
	"mission_version_mismatch" in stf.deny_reasons with input as i
}

test_expired_window_is_denied if {
	m := object.union(base_mission, {"time_window": {"start": "2000-01-01T00:00:00Z", "end": "2000-01-02T00:00:00Z"}})
	"outside_time_window" in stf.deny_reasons with input as object.union(base_input, {"mission": m})
}

test_r3_needs_creator_approval if {
	i := object.union(base_input, {"risk_class": "R3"})
	not stf.allow with input as i
	"creator_approval_required" in stf.deny_reasons with input as i
	stf.allow with input as object.union(i, {"creator_approval_reference": "approval:1"})
}

test_null_or_empty_approval_is_not_approval if {
	i := object.union(base_input, {"risk_class": "R4", "creator_approval_reference": ""})
	not stf.allow with input as i
}

test_r5_is_never_allowed_inside_a_mission if {
	i := object.union(base_input, {"risk_class": "R5", "creator_approval_reference": "approval:1"})
	not stf.allow with input as i
	"new_mission_required" in stf.deny_reasons with input as i
}

test_ceiling_is_enforced if {
	m := object.union(base_mission, {"risk_ceiling": "R1"})
	"risk_ceiling_exceeded" in stf.deny_reasons with input as object.union(base_input, {"mission": m})
}

test_unknown_risk_class_is_denied if {
	not stf.allow with input as object.union(base_input, {"risk_class": "R9"})
}
