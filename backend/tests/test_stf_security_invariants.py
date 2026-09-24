from datetime import datetime, timedelta, timezone

from app.security_task_force.evidence import EvidenceRecord
from app.security_task_force.grants import CapabilityGrant
from app.security_task_force.verification import verify_finding


def grant(**overrides):
    data = {
        "grant_id": "g",
        "mission_id": "m",
        "mission_version": 1,
        "actor": "a",
        "capability": "c",
        "target_id": "t",
        "environment": "CYBER_RANGE",
        "action_class": "validate",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "max_invocations": 1,
    }
    data.update(overrides)
    return CapabilityGrant(**data)


def permitted(grant_value, *, environment="CYBER_RANGE", invocations=0):
    return grant_value.permits(
        mission_id="m",
        mission_version=1,
        actor="a",
        capability="c",
        target_id="t",
        environment=environment,
        action_class="validate",
        invocations=invocations,
    )


def test_grant_rejects_cross_environment_replay_and_budget():
    value = grant()
    assert permitted(value)
    assert not permitted(value, environment="REAL_AUTHORIZED")
    assert not permitted(value, invocations=1)


def test_revoked_and_expired_grants_fail_closed():
    assert not permitted(grant(revoked=True))
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert not permitted(grant(expires_at=expired))


def test_verification_requires_integrity_purple_and_replay():
    evidence = EvidenceRecord.build(
        evidence_id="e",
        mission_id="m",
        action_id="a",
        source="range",
        acquired_at="now",
        payload={"ok": True},
    )
    result = verify_finding(
        evidence,
        None,
        purple_required=True,
        reproduced=True,
    )
    assert result.status == "probable"
    result = verify_finding(
        evidence,
        evidence,
        purple_required=True,
        reproduced=False,
    )
    assert result.status == "not_reproduced"
    result = verify_finding(
        evidence,
        evidence,
        purple_required=True,
        reproduced=True,
    )
    assert result.status == "confirmed"
