from __future__ import annotations

from datetime import datetime, timezone

from app.security_task_force.contracts import RiskClass
from app.security_task_force.training import (
    ADVANCED_CAMPAIGN_ID,
    RANGE_ENVIRONMENT_ID,
    TRAINING_AGENT_SPECS,
    TrainingHistory,
    build_training_actions,
    compile_training_contract,
    select_next_training_agent,
)

from app.security_task_force.contracts import RiskClass


def test_training_roster_has_exactly_ten_distinct_security_specialists() -> None:
    assert len(TRAINING_AGENT_SPECS) == 10
    assert len({item.code for item in TRAINING_AGENT_SPECS}) == 10
    assert len({item.specialty for item in TRAINING_AGENT_SPECS}) == 10
    assert all(item.code.startswith("stf-") for item in TRAINING_AGENT_SPECS)


def test_training_contract_is_range_only_and_never_self_escalates() -> None:
    spec = TRAINING_AGENT_SPECS[0]
    compiled = compile_training_contract("creator-1", spec)

    assert compiled.status == "COMPILED"
    assert compiled.contract is not None
    contract = compiled.contract
    assert contract.authorized_environments == [RANGE_ENVIRONMENT_ID]
    assert contract.authorized_targets == [ADVANCED_CAMPAIGN_ID]
    assert contract.excluded_targets == ["real:*"]
    assert contract.risk_ceiling is RiskClass.R2
    assert contract.allowed_action_classes == ["range.training"]


def test_training_plan_drives_the_advanced_campaign_to_completion() -> None:
    spec = TRAINING_AGENT_SPECS[3]
    compiled = compile_training_contract("creator-1", spec)
    assert compiled.contract is not None

    actions = build_training_actions(compiled.contract, spec, cycle=7)

    assert [item.capability for item in actions] == [
        "range.campaign.start",
        "range.campaign.advance",
        "range.campaign.advance",
        "range.campaign.advance",
        "range.campaign.verify",
    ]
    assert all(item.environment_id == RANGE_ENVIRONMENT_ID for item in actions)
    assert all(item.target_id == ADVANCED_CAMPAIGN_ID for item in actions)
    assert all(item.action_class == "range.training" for item in actions)
    assert all(item.actor == f"agent:{spec.code}" for item in actions)
    assert len({item.action_id for item in actions}) == len(actions)
    assert len({item.idempotency_key for item in actions}) == len(actions)
    assert max(item.risk_class.rank for item in actions) <= RiskClass.R2.rank


def test_round_robin_prefers_untrained_then_least_recent_agent() -> None:
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    specs = TRAINING_AGENT_SPECS[:3]

    first = select_next_training_agent(
        specs,
        {
            specs[0].code: TrainingHistory(cycles=2, last_started_at=now),
            specs[1].code: TrainingHistory(cycles=1, last_started_at=now),
        },
    )
    assert first.code == specs[2].code

    second = select_next_training_agent(
        specs,
        {
            specs[0].code: TrainingHistory(cycles=2, last_started_at=now),
            specs[1].code: TrainingHistory(cycles=1, last_started_at=now),
            specs[2].code: TrainingHistory(cycles=1, last_started_at=datetime(2026, 10, 2, tzinfo=timezone.utc)),
        },
    )
    assert second.code == specs[2].code
