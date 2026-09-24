from datetime import datetime, timedelta, timezone

from app.security_task_force.authorization import authorize
from app.security_task_force.contracts import ActionRequest, Environment, MissionContract, RiskClass


def contract() -> MissionContract:
    now = datetime.now(timezone.utc)
    return MissionContract(
        mission_id="m1", creator_id="c1", objective="validate range", success_criteria=["evidence"],
        authorized_targets=["juice-shop"], excluded_targets=[], authorized_environments=[Environment.CYBER_RANGE],
        allowed_action_classes=["validate"], risk_ceiling=RiskClass.R4,
        time_window={"start": now, "end": now + timedelta(hours=1)}, mission_version=1,
    )


def action(**overrides) -> ActionRequest:
    data=dict(action_id="a1",mission_id="m1",mission_version=1,task_id="t1",actor="agent:red",target_id="juice-shop",
              environment=Environment.CYBER_RANGE,capability="range.validate",action_class="validate",risk_class=RiskClass.R2,idempotency_key="k1")
    data.update(overrides)
    return ActionRequest(**data)


def test_range_action_is_permitted_in_declared_scope():
    assert authorize(contract(), action()).decision == "permit"


def test_cross_environment_fails_closed():
    result=authorize(contract(), action(environment=Environment.REAL_AUTHORIZED))
    assert result.decision == "deny"
    assert "environment_not_authorized" in result.reason_codes


def test_r3_requires_creator_approval():
    assert authorize(contract(), action(risk_class=RiskClass.R3)).decision == "escalate"
    assert authorize(contract(), action(risk_class=RiskClass.R3), creator_approval_reference="approval:1").decision == "permit"


def test_r5_never_executes_inside_existing_mission():
    assert authorize(contract(), action(risk_class=RiskClass.R5)).decision == "escalate"
