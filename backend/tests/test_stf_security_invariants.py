from datetime import datetime, timedelta, timezone

from app.security_task_force.evidence import EvidenceRecord
from app.security_task_force.grants import CapabilityGrant
from app.security_task_force.verification import verify_finding


def grant(**kw):
    data=dict(grant_id="g",mission_id="m",mission_version=1,actor="a",capability="c",target_id="t",environment="CYBER_RANGE",action_class="validate",expires_at=datetime.now(timezone.utc)+timedelta(minutes=5),max_invocations=1)
    data.update(kw)
    return CapabilityGrant(**data)


def test_grant_rejects_cross_environment_replay_and_budget():
    g=grant()
    assert g.permits(mission_id="m",mission_version=1,actor="a",capability="c",target_id="t",environment="CYBER_RANGE",action_class="validate",invocations=0)
    assert not g.permits(mission_id="m",mission_version=1,actor="a",capability="c",target_id="t",environment="REAL_AUTHORIZED",action_class="validate",invocations=0)
    assert not g.permits(mission_id="m",mission_version=1,actor="a",capability="c",target_id="t",environment="CYBER_RANGE",action_class="validate",invocations=1)


def test_revoked_and_expired_grants_fail_closed():
    assert not grant(revoked=True).permits(mission_id="m",mission_version=1,actor="a",capability="c",target_id="t",environment="CYBER_RANGE",action_class="validate",invocations=0)
    assert not grant(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)).permits(mission_id="m",mission_version=1,actor="a",capability="c",target_id="t",environment="CYBER_RANGE",action_class="validate",invocations=0)


def test_verification_requires_integrity_purple_and_replay():
    e=EvidenceRecord.build(evidence_id="e",mission_id="m",action_id="a",source="range",acquired_at="now",payload={"ok":True})
    assert verify_finding(e,None,purple_required=True,reproduced=True).status=="probable"
    assert verify_finding(e,e,purple_required=True,reproduced=False).status=="not_reproduced"
    assert verify_finding(e,e,purple_required=True,reproduced=True).status=="confirmed"
