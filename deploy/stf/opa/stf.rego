package creation.stf

import rego.v1

# Default deny: any missing input, engine error or unmatched rule ends in "not allowed".
default allow := false

risk_rank := {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}

has_approval if {
	is_string(input.creator_approval_reference)
	input.creator_approval_reference != ""
}

deny_reasons contains "mission_version_mismatch" if input.mission_version != input.mission.mission_version

deny_reasons contains "mission_version_mismatch" if input.mission_id != input.mission.mission_id

deny_reasons contains "environment_not_authorized" if not input.environment_id in input.mission.authorized_environments

deny_reasons contains "target_not_authorized" if not input.target_id in input.mission.authorized_targets

deny_reasons contains "target_not_authorized" if input.target_id in input.mission.excluded_targets

deny_reasons contains "action_class_not_authorized" if not input.action_class in input.mission.allowed_action_classes

# A window that is present but cannot be parsed (or is out of the nanosecond range) would make the
# comparisons below undefined, and an undefined deny rule silently allows. Refuse it explicitly.
window_present if input.mission.time_window.start

window_valid if {
	start := time.parse_rfc3339_ns(input.mission.time_window.start)
	end := time.parse_rfc3339_ns(input.mission.time_window.end)
	start < end
}

deny_reasons contains "time_window_invalid" if {
	window_present
	not window_valid
}

deny_reasons contains "outside_time_window" if time.now_ns() < time.parse_rfc3339_ns(input.mission.time_window.start)

deny_reasons contains "outside_time_window" if time.now_ns() >= time.parse_rfc3339_ns(input.mission.time_window.end)

deny_reasons contains "risk_ceiling_exceeded" if risk_rank[input.risk_class] > risk_rank[input.mission.risk_ceiling]

deny_reasons contains "new_mission_required" if input.risk_class == "R5"

deny_reasons contains "creator_approval_required" if {
	input.risk_class in {"R3", "R4"}
	not has_approval
}

# An unknown risk class has no rank, so the comparison above is undefined: refuse it explicitly.
deny_reasons contains "unknown_risk_class" if not input.risk_class in object.keys(risk_rank)

# Deny rules stay undefined when their input is missing, so an empty deny set alone would mean
# "allowed" for an empty request. Permission therefore also needs a well-formed request.
well_formed if {
	is_string(input.mission_id)
	is_string(input.target_id)
	is_string(input.environment_id)
	is_string(input.action_class)
	is_string(input.risk_class)
	is_number(input.mission_version)
	is_object(input.mission)
	is_string(input.mission.mission_id)
	is_number(input.mission.mission_version)
	is_string(input.mission.risk_ceiling)
}

allow if {
	well_formed
	count(deny_reasons) == 0
}

# The Authorization Plane queries this document.
decision := {"allow": allow, "reasons": sort([reason | some reason in deny_reasons])}
