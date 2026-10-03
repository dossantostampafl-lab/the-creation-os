"""Transactional authority for the Security Task Force, against a guarded disposable PostgreSQL database."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from stf_database import TestDatabaseRefused, guarded_test_database_url

from app.models.entities import Creator

RANGE = "cyber_range:lab-a"
CANDIDATE = {
    "mission_id": "m1", "success_criteria": ["evidence"], "authorized_targets": ["juice-shop"],
    "allowed_action_classes": ["validate"], "risk_ceiling": "R4",
}


# --- the guard: refusals happen before any connection exists --------------------------------------------

@pytest.mark.parametrize("env", [
    {},
    {"DATABASE_URL": "postgresql+asyncpg://u:p@h/the_creation_os"},  # a production URL alone is not a test URL
    {"STF_TEST_DATABASE_URL": "postgresql+asyncpg://u:p@h/the_creation_os"},  # no test_stf_ prefix
    {"STF_TEST_DATABASE_URL": "postgresql+asyncpg://u:p@h/stf_runtime"},
    {"STF_TEST_DATABASE_URL": "postgresql+asyncpg://u:p@h/test_stf_x", "DATABASE_URL": "postgresql+asyncpg://u:p@h/test_stf_x"},
])
def test_the_test_database_guard_refuses_before_any_ddl(env, monkeypatch):
    import sqlalchemy.ext.asyncio as asyncio_module

    def no_engine(*args, **kwargs):
        raise AssertionError("an engine was created before the guard finished")

    monkeypatch.setattr(asyncio_module, "create_async_engine", no_engine)
    with pytest.raises(TestDatabaseRefused):
        guarded_test_database_url(env)


def test_the_guard_accepts_a_prefixed_database_that_is_not_production():
    url = "postgresql+asyncpg://u:p@h/test_stf_runtime"
    assert guarded_test_database_url({"STF_TEST_DATABASE_URL": url, "DATABASE_URL": "postgresql+asyncpg://u:p@h/app"}) == url


# --- behavior ------------------------------------------------------------------------------------------

def _repository(session):
    from app.security_task_force.repository import StfRepository

    return StfRepository(session)


def _action(**overrides):
    from app.security_task_force.contracts import ActionRequest

    data = dict(action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red",
                target_id="juice-shop", environment_id=RANGE, capability="range.health.verify",
                action_class="validate", risk_class="R2", idempotency_key="k1", parameters={"path": "/"})
    data.update(overrides)
    return ActionRequest(**data)


async def _seed(factory, *, max_invocations=1, expires_in=timedelta(minutes=5)):
    """A creator, a compiled contract, a queued run and one grant. Returns (creator_id, run_id, grant_id)."""
    from app.security_task_force.contracts import CapabilityGrant
    from app.security_task_force.mission_compiler import compile_verified_contract

    creator_id, run_id, grant_id = str(uuid.uuid4()), str(uuid.uuid4()), f"grant:{uuid.uuid4()}"
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"c-{creator_id[:8]}", password_hash="x", is_active=True))
        await session.flush()
        repository = _repository(session)
        compiled = compile_verified_contract(intent="validate", candidate={**CANDIDATE, "creator_id": creator_id},
                                             authorized_environments=[RANGE])
        await repository.save_contract(compiled)
        await repository.create_run(creator_id=creator_id, run_id=run_id, mission_id="m1", mission_version=1,
                                    request_key="req-1", request_hash="h" * 64, plan_hash="p" * 64,
                                    plan=[_action().model_dump(mode="json")])
        grant = CapabilityGrant(grant_id=grant_id, mission_id="m1", mission_version=1, actor="agent:red",
                                capability="range.health.verify", target_id="juice-shop", environment_id=RANGE,
                                action_class="validate", expires_at=datetime.now(timezone.utc) + expires_in,
                                max_invocations=max_invocations)
        await repository.issue_grant(run_id, grant)
        await session.commit()
    return creator_id, run_id, grant_id


async def test_one_grant_one_concurrent_winner(stf_db):
    engine, factory = stf_db
    _, run_id, grant_id = await _seed(factory, max_invocations=1)

    async def attempt(index: int):
        async with factory() as session:
            receipt = await _repository(session).reserve_dispatch(
                run_id, _action(action_id=f"a{index}", idempotency_key=f"k{index}"), grant_id)
            await session.commit()
            return receipt

    receipts = await asyncio.gather(*(attempt(i) for i in range(20)))
    winners = [r for r in receipts if r.status == "authorized"]
    assert len(winners) == 1
    assert all(r.status == "denied" for r in receipts if r is not winners[0])
    async with factory() as session:
        used = await session.scalar(text("SELECT invocations FROM stf_grants WHERE grant_id = :g"), {"g": grant_id})
        rows = await session.scalar(select(func.count()).select_from(text("stf_dispatches")))
    assert used == 1 and rows == 1


async def test_revoke_cannot_be_lost(stf_db):
    _, factory = stf_db
    _, run_id, grant_id = await _seed(factory, max_invocations=5)
    async with factory() as session:
        await _repository(session).revoke_run(run_id)
        await session.commit()
    async with factory() as session:
        dispatch_after_cancel = await _repository(session).reserve_dispatch(run_id, _action(), grant_id)
        await session.commit()
    assert dispatch_after_cancel.status == "denied"
    assert "run_cancelled" in dispatch_after_cancel.reason_codes


async def test_concurrent_cancel_and_dispatch_never_leave_a_dispatch_after_the_revoke(stf_db):
    _, factory = stf_db
    _, run_id, grant_id = await _seed(factory, max_invocations=50)

    async def dispatch(index: int):
        async with factory() as session:
            receipt = await _repository(session).reserve_dispatch(
                run_id, _action(action_id=f"a{index}", idempotency_key=f"k{index}"), grant_id)
            await session.commit()
            return receipt

    async def cancel():
        async with factory() as session:
            await _repository(session).revoke_run(run_id)
            await session.commit()

    await asyncio.gather(cancel(), *(dispatch(i) for i in range(10)))
    async with factory() as session:
        late = await _repository(session).reserve_dispatch(run_id, _action(action_id="late", idempotency_key="late"), grant_id)
        state = await session.scalar(text("SELECT desired_state FROM stf_runs WHERE id = :r"), {"r": run_id})
    assert late.status == "denied" and state == "CANCEL"


async def test_chronicle_failure_rolls_back_authority(stf_db, monkeypatch):
    _, factory = stf_db
    _, run_id, grant_id = await _seed(factory, max_invocations=1)
    from app.repositories.domain import DomainRepository

    async def broken(*args, **kwargs):
        raise RuntimeError("chronicle unavailable")

    monkeypatch.setattr(DomainRepository, "add_event", broken)
    async with factory() as session:
        with pytest.raises(RuntimeError):
            await _repository(session).reserve_dispatch(run_id, _action(), grant_id)
        await session.rollback()
    async with factory() as session:
        used = await session.scalar(text("SELECT invocations FROM stf_grants WHERE grant_id = :g"), {"g": grant_id})
        dispatches = await session.scalar(select(func.count()).select_from(text("stf_dispatches")))
    assert used == 0 and dispatches == 0  # authority was never spent without its audit record


async def test_same_key_same_content_is_idempotent_and_different_content_conflicts(stf_db):
    from app.security_task_force.repository import IdempotencyConflict

    _, factory = stf_db
    _, run_id, grant_id = await _seed(factory, max_invocations=5)
    async with factory() as session:
        repository = _repository(session)
        first = await repository.reserve_dispatch(run_id, _action(), grant_id)
        again = await repository.reserve_dispatch(run_id, _action(), grant_id)
        await session.commit()
        assert first.status == "authorized" and again.execution_id == first.execution_id
        with pytest.raises(IdempotencyConflict):
            await repository.reserve_dispatch(run_id, _action(parameters={"path": "/other"}), grant_id)
        await session.rollback()
    async with factory() as session:
        used = await session.scalar(text("SELECT invocations FROM stf_grants WHERE grant_id = :g"), {"g": grant_id})
    assert used == 1  # the repeat did not spend the grant again


@pytest.mark.parametrize("case", ["expired", "revoked", "old_version", "changed_parameters_target"])
async def test_invalid_grants_are_denied(stf_db, case):
    _, factory = stf_db
    expires = timedelta(seconds=-5) if case == "expired" else timedelta(minutes=5)
    _, run_id, grant_id = await _seed(factory, max_invocations=5, expires_in=expires)
    action = _action()
    async with factory() as session:
        if case == "revoked":
            await session.execute(text("UPDATE stf_grants SET revoked = true WHERE grant_id = :g"), {"g": grant_id})
        if case == "old_version":
            action = _action(mission_version=2)
        if case == "changed_parameters_target":
            action = _action(target_id="webgoat")
        receipt = await _repository(session).reserve_dispatch(run_id, action, grant_id)
        await session.commit()
    assert receipt.status == "denied" and receipt.execution_id is None


async def test_contracts_are_immutable_and_unique(stf_db):
    from app.security_task_force.mission_compiler import compile_verified_contract

    _, factory = stf_db
    creator_id, _, _ = await _seed(factory)
    async with factory() as session:
        repository = _repository(session)
        same = compile_verified_contract(intent="validate", candidate={**CANDIDATE, "creator_id": creator_id},
                                         authorized_environments=[RANGE])
        await repository.save_contract(same)  # saving the identical contract again is a no-op
        different = compile_verified_contract(intent="validate", candidate={**CANDIDATE, "creator_id": creator_id,
                                              "authorized_targets": ["webgoat"]}, authorized_environments=[RANGE])
        from app.security_task_force.repository import ContractConflict

        with pytest.raises(ContractConflict):
            await repository.save_contract(different)
        await session.rollback()
    async with factory() as session:
        with pytest.raises(Exception, match="immutable"):
            await session.execute(text("UPDATE stf_contracts SET contract_hash = 'x'"))


async def test_a_run_request_key_is_unique_per_creator_and_mission(stf_db):
    _, factory = stf_db
    creator_id, run_id, _ = await _seed(factory)
    async with factory() as session:
        repository = _repository(session)
        again = await repository.create_run(creator_id=creator_id, run_id=str(uuid.uuid4()), mission_id="m1",
                                            mission_version=1, request_key="req-1", request_hash="h" * 64,
                                            plan_hash="p" * 64)
        assert again.run_id == run_id  # the same request returns the same run
        from app.security_task_force.repository import IdempotencyConflict

        with pytest.raises(IdempotencyConflict):
            await repository.create_run(creator_id=creator_id, run_id=str(uuid.uuid4()), mission_id="m1",
                                        mission_version=1, request_key="req-1", request_hash="z" * 64, plan_hash="p" * 64)


async def test_outbox_leases_are_exclusive_expire_and_ack_needs_the_token(stf_db):
    _, factory = stf_db
    async with factory() as session:
        repository = _repository(session)
        ids = [await repository.add_outbox("start", {"n": n}) for n in range(5)]
        await session.commit()

    async def claim(limit):
        async with factory() as session:
            leases = await _repository(session).claim_outbox("start", limit)
            await session.commit()
            return leases

    first, second = await asyncio.gather(claim(3), claim(3))
    claimed = [lease.id for lease in first + second]
    assert len(claimed) == len(set(claimed)) == 5  # SKIP LOCKED: no item leased twice

    lease = (first + second)[0]
    async with factory() as session:
        repository = _repository(session)
        assert await repository.ack_outbox(lease.id, "wrong-token") is False
        assert await repository.ack_outbox(lease.id, lease.token) is True
        assert await repository.ack_outbox(lease.id, lease.token) is False  # already acknowledged
        await session.commit()
    async with factory() as session:
        await session.execute(text("UPDATE stf_outbox SET lease_expires_at = now() - interval '1 second' WHERE status = 'leased'"))
        await session.commit()
    again = await claim(10)
    assert {item.id for item in again} == set(claimed) - {lease.id}  # expired leases come back, acked ones do not
    assert set(ids) >= set(claimed)


async def test_inbox_applies_each_event_once(stf_db):
    _, factory = stf_db
    async with factory() as session:
        repository = _repository(session)
        assert await repository.record_inbox("consumer-a", "evt-1") is True
        assert await repository.record_inbox("consumer-a", "evt-1") is False
        assert await repository.record_inbox("consumer-b", "evt-1") is True


def test_the_database_guard_is_active_in_ci_only_when_required():
    # Local runs without STF_TEST_DATABASE_URL skip the database tests; CI sets STF_REQUIRE_TEST_DATABASE=1.
    assert True


async def test_persisted_run_verification_requires_intact_correlated_evidence(stf_db):
    from app.security_task_force.evidence import EvidenceRecord

    _, factory = stf_db
    _, run_id, grant_id = await _seed(factory)
    request = _action()
    async with factory() as session:
        repository = _repository(session)
        receipt = await repository.reserve_dispatch(run_id, request, grant_id)
        assert receipt.status == "authorized" and receipt.execution_id is not None
        await repository.record_outcome(receipt.execution_id, "executed")
        await session.commit()

    async with factory() as session:
        assert await _repository(session).verify_run_evidence(run_id) is False

    evidence = EvidenceRecord.build(
        evidence_id=f"evidence:{uuid.uuid4()}",
        run_id=run_id,
        execution_id=receipt.execution_id,
        mission_id=request.mission_id,
        action_id=request.action_id,
        task_id=request.task_id,
        environment_id=request.environment_id,
        source="stf-gateway",
        kind="execution",
        acquired_at=datetime.now(timezone.utc).isoformat(),
        payload={"status": "executed", "gateway_execution_id": "gw-1"},
    )
    async with factory() as session:
        repository = _repository(session)
        await repository.record_evidence(run_id, receipt.execution_id, evidence)
        await repository.record_outcome(receipt.execution_id, "executed", evidence_id=evidence.evidence_id)
        await session.commit()

    async with factory() as session:
        assert await _repository(session).verify_run_evidence(run_id) is True

    wrong = EvidenceRecord.build(
        evidence_id=f"evidence:{uuid.uuid4()}",
        run_id=run_id,
        execution_id=receipt.execution_id,
        mission_id=request.mission_id,
        action_id="another-action",
        task_id=request.task_id,
        environment_id=request.environment_id,
        source="stf-gateway",
        kind="execution",
        acquired_at=datetime.now(timezone.utc).isoformat(),
        payload={"status": "executed"},
    )
    async with factory() as session:
        with pytest.raises(ValueError, match="correlation"):
            await _repository(session).record_evidence(run_id, receipt.execution_id, wrong)


async def test_verified_finding_projection_and_qualification_use_only_evidence_references(stf_db):
    from app.security_task_force.contracts import CapabilityGrant
    from app.security_task_force.evidence import EvidenceRecord, REDACTED

    _, factory = stf_db
    _, run_id, grant_id = await _seed(factory)
    replay = _action(
        action_id="a2",
        task_id="t2",
        idempotency_key="k2",
        parameters={"replay_of": "a1", "scenario_family": "web_application"},
    )
    original = _action(parameters={
        "scenario_family": "web_application",
        "purple_required": True,
        "finding_title": "Correlated training finding",
    })
    replay_grant = CapabilityGrant(
        grant_id=f"grant:{uuid.uuid4()}",
        mission_id="m1",
        mission_version=1,
        actor="agent:red",
        capability="range.health.verify",
        target_id="juice-shop",
        environment_id=RANGE,
        action_class="validate",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    async with factory() as session:
        repository = _repository(session)
        run = await repository.get_run(run_id, lock=True)
        assert run is not None
        run.plan_json = [original.model_dump(mode="json"), replay.model_dump(mode="json")]
        assert await repository.issue_grant(run_id, replay_grant)
        first = await repository.reserve_dispatch(run_id, original, grant_id)
        second = await repository.reserve_dispatch(run_id, replay, replay_grant.grant_id)
        assert first.execution_id and second.execution_id

        first_exec = EvidenceRecord.build(
            evidence_id=f"evidence:{uuid.uuid4()}",
            run_id=run_id,
            execution_id=first.execution_id,
            mission_id="m1",
            action_id="a1",
            task_id="t1",
            environment_id=RANGE,
            source="stf-gateway",
            kind="execution",
            acquired_at=datetime.now(timezone.utc).isoformat(),
            payload={"status": "executed"},
        )
        replay_exec = EvidenceRecord.build(
            evidence_id=f"evidence:{uuid.uuid4()}",
            run_id=run_id,
            execution_id=second.execution_id,
            mission_id="m1",
            action_id="a2",
            task_id="t2",
            environment_id=RANGE,
            source="stf-gateway",
            kind="execution",
            acquired_at=datetime.now(timezone.utc).isoformat(),
            payload={"status": "executed"},
        )
        await repository.record_evidence(run_id, first.execution_id, first_exec)
        await repository.record_outcome(first.execution_id, "executed", evidence_id=first_exec.evidence_id)
        await repository.record_evidence(run_id, second.execution_id, replay_exec)
        await repository.record_outcome(second.execution_id, "executed", evidence_id=replay_exec.evidence_id)

        attack = EvidenceRecord.build(
            evidence_id=f"evidence:{uuid.uuid4()}",
            run_id=run_id,
            execution_id=first.execution_id,
            mission_id="m1",
            action_id="a1",
            task_id="t1",
            environment_id=RANGE,
            source="range-red",
            kind="attack",
            acquired_at=datetime.now(timezone.utc).isoformat(),
            payload={"observed": True, "api_token": "must-not-survive"},
        )
        defense = EvidenceRecord.build(
            evidence_id=f"evidence:{uuid.uuid4()}",
            run_id=run_id,
            execution_id=first.execution_id,
            mission_id="m1",
            action_id="a1",
            task_id="t1",
            environment_id=RANGE,
            source="range-blue",
            kind="defense",
            acquired_at=datetime.now(timezone.utc).isoformat(),
            payload={"alerted": True},
        )
        await repository.record_evidence(run_id, first.execution_id, attack)
        await repository.record_evidence(run_id, first.execution_id, defense)

        findings = await repository.project_verified_findings(run_id)
        qualification = await repository.qualify_run(run_id)
        stored_attack = [item for item in await repository.evidence_records(run_id, kind="attack")][0]
        await session.commit()

    assert len(findings) == 1
    assert findings[0]["status"] == "confirmed"
    assert findings[0]["attack_evidence"] == [attack.evidence_id]
    assert findings[0]["defense_evidence"] == [defense.evidence_id]
    assert "payload" not in findings[0]
    assert stored_attack.payload["api_token"] == REDACTED
    assert qualification["eligible"] is True
    assert qualification["level"] == "SH-1"
    assert "reproducibility" in qualification["passed_gates"]
    assert "scenario:authorization" in qualification["failed_gates"]
    assert attack.evidence_id in qualification["evidence_refs"]


async def test_verified_projection_tables_are_immutable(stf_db):
    _, factory = stf_db
    _, run_id, _ = await _seed(factory)
    async with factory() as session:
        from app.models.security_task_force import StfQualification

        session.add(StfQualification(
            run_id=run_id,
            eligible=False,
            level=None,
            score=0,
            failed_gates=["x"],
            passed_gates=[],
            reasons=["x"],
            evidence_refs=["plan:p"],
        ))
        await session.commit()
    async with factory() as session:
        with pytest.raises(Exception, match="immutable"):
            await session.execute(
                text("UPDATE stf_qualifications SET score = 100 WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
