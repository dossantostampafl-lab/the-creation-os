from datetime import datetime, timedelta, timezone

from app.security_task_force.contracts import ActionRequest, RiskClass
from app.security_task_force.evidence import EvidenceRecord
from app.security_task_force.grants import GrantStore
from app.security_task_force.verification import verify_finding

RANGE = "cyber_range:lab-a"


def action(**overrides) -> ActionRequest:
    data = dict(action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red",
                target_id="juice-shop", environment_id=RANGE, capability="range.validate",
                action_class="validate", risk_class=RiskClass.R2, idempotency_key="k1")
    data.update(overrides)
    return ActionRequest(**data)


def test_grant_rejects_cross_environment_replay_and_budget(tmp_path):
    store = GrantStore(tmp_path / "grants.json")
    request = action()
    grant = store.issue(request)
    assert store.consume(grant.grant_id, request)
    assert not store.consume(grant.grant_id, request)  # budget of one
    other = store.issue(request)
    assert not store.allows(other.grant_id, action(environment_id="real:prod-a"))


def test_revoked_expired_and_stale_version_grants_fail_closed(tmp_path):
    store = GrantStore(tmp_path / "grants.json")
    request = action()
    revoked = store.issue(request)
    store.revoke(revoked.grant_id)
    assert not store.allows(revoked.grant_id, request)
    expired = store.issue(request, now=datetime.now(timezone.utc) - timedelta(hours=1))
    assert not store.allows(expired.grant_id, request)
    fresh = store.issue(request)
    assert GrantStore(tmp_path / "grants.json").allows(fresh.grant_id, request)  # survives restart
    store.revoke_mission("m1", below_version=1)
    assert not GrantStore(tmp_path / "grants.json").allows(fresh.grant_id, request)


def _evidence(kind="attack", environment=RANGE):
    return EvidenceRecord.build(evidence_id="e", mission_id="m1", action_id="a1", environment_id=environment,
                                source="range", acquired_at="now", payload={"ok": True, "token": "s3cret"}, kind=kind)


def test_evidence_is_redacted_and_tamper_evident():
    record = _evidence()
    assert record.payload["token"] == "[redacted]"
    assert record.integrity_ok()
    assert not EvidenceRecord(**{**record.__dict__, "environment_id": "real:prod-a"}).integrity_ok()


def test_verification_requires_integrity_purple_replay_and_matching_environment():
    attack = _evidence()
    assert verify_finding(attack, None, purple_required=True, reproduced=True).status == "probable"
    assert verify_finding(attack, _evidence("defense"), purple_required=True, reproduced=False).status == "not_reproduced"
    assert verify_finding(attack, _evidence("defense"), purple_required=True, reproduced=True).status == "confirmed"
    assert verify_finding(attack, _evidence("defense", "cyber_range:lab-b"), purple_required=True, reproduced=True).status == "rejected"
    assert verify_finding(None, None, purple_required=False, reproduced=True).status == "hypothesis"
