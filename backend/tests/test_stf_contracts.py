from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.security_task_force.authorization import authorize
from app.security_task_force.contracts import ActionRequest, MissionContract, RiskClass

RANGE = "cyber_range:lab-a"


def contract(**overrides) -> MissionContract:
    now = datetime.now(timezone.utc)
    data = dict(
        mission_id="m1", creator_id="c1", objective="validate range", success_criteria=["evidence"],
        authorized_targets=["juice-shop"], excluded_targets=[], authorized_environments=[RANGE],
        allowed_action_classes=["validate"], risk_ceiling=RiskClass.R4,
        time_window={"start": now - timedelta(minutes=1), "end": now + timedelta(hours=1)}, mission_version=1,
    )
    data.update(overrides)
    return MissionContract(**data)


def action(**overrides) -> ActionRequest:
    data = dict(action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red",
                target_id="juice-shop", environment_id=RANGE, capability="range.validate",
                action_class="validate", risk_class=RiskClass.R2, idempotency_key="k1")
    data.update(overrides)
    return ActionRequest(**data)


def test_contract_requires_an_authorized_environment():
    with pytest.raises(ValidationError):
        contract(authorized_environments=[])


def test_environments_are_explicit_and_normalized():
    assert contract(authorized_environments=[RANGE, RANGE]).authorized_environments == [RANGE]
    with pytest.raises(ValidationError):
        contract(authorized_environments=["CYBER_RANGE"])


def test_normalized_payload_is_key_sorted():
    payload = contract().normalized_payload()
    assert list(payload) == sorted(payload)


def test_range_action_is_permitted_in_declared_scope():
    assert authorize(contract(), action()).decision == "permit"


def test_cross_environment_fails_closed():
    result = authorize(contract(), action(environment_id="real:prod-a"))
    assert result.decision == "deny"
    assert "environment_not_authorized" in result.reason_codes


def test_r3_requires_creator_approval():
    assert authorize(contract(), action(risk_class=RiskClass.R3)).decision == "escalate"
    assert authorize(contract(), action(risk_class=RiskClass.R3), creator_approval_reference="approval:1").decision == "permit"


def test_r5_never_executes_inside_existing_mission():
    assert authorize(contract(), action(risk_class=RiskClass.R5)).decision == "escalate"


def test_outside_time_window_is_denied():
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    assert authorize(contract(), action(), now=later).reason_codes == ["outside_time_window"]


def test_time_window_beyond_the_policy_engine_range_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        contract(time_window={"start": now, "end": now.replace(year=2999)})
