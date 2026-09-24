package creation.stf

default allow := false

risk_rank := {"R0":0,"R1":1,"R2":2,"R3":3,"R4":4,"R5":5}

allow if {
  input.environment in input.mission.authorized_environments
  input.target_id in input.mission.authorized_targets
  not input.target_id in input.mission.excluded_targets
  input.action_class in input.mission.allowed_action_classes
  risk_rank[input.risk_class] <= risk_rank[input.mission.risk_ceiling]
  input.risk_class != "R5"
  not requires_creator_approval
}

requires_creator_approval if {
  input.risk_class in {"R3","R4"}
  not input.creator_approval_reference
}
