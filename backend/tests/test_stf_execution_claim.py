from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.entities import Creator
from app.security_task_force.canonicalize import canonical_hash
from app.security_task_force.contracts import ActionRequest, CapabilityGrant
from app.security_task_force.mission_compiler import compile_verified_contract
from app.security_task_force.repository import StfRepository

pytestmark = pytest.mark.integration
RANGE = "cyber_range:lab-a"


def action() -> ActionRequest:
    return ActionRequest(
        action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red",
        target_id="juice-shop", environment_id=RANGE, capability="range.health.verify",
        action_class="validate", risk_class="R1", idempotency_key="k1", parameters={"path": "/"},
    )


async def seeded(factory):
    creator_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
    request = action()
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"c-{creator_id[:8]}", password_hash="x", is_active=True))
        await session.flush()
        compiled = compile_verified_contract(
            intent="validate",
            candidate={
                "mission_id": "m1", "creator_id": creator_id, "success_criteria": ["evidence"],
                "authorized_targets": ["juice-shop"], "allowed_action_classes": ["validate"], "risk_ceiling": "R4",
            },
            authorized_environments=[RANGE],
        )
        repository = StfRepository(session)
        await repository.save_contract(compiled)
        plan = [request.model_dump(mode="json")]
        await repository.create_run(
            creator_id=creator_id, run_id=run_id, mission_id="m1", mission_version=1,
            request_key="req-1", request_hash=canonical_hash(plan), plan_hash=canonical_hash(plan), plan=plan,
        )
        grant = CapabilityGrant(
            grant_id=f"grant:{uuid.uuid4()}", mission_id="m1", mission_version=1, actor="agent:red",
            capability="range.health.verify", target_id="juice-shop", environment_id=RANGE,
            action_class="validate", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), max_invocations=1,
        )
        await repository.issue_grant(run_id, grant)
        receipt = await repository.reserve_dispatch(run_id, request, grant.grant_id)
        contract = await repository.get_contract(creator_id, "m1", 1)
        await session.commit()
    assert receipt.execution_id and contract is not None
    return run_id, receipt.execution_id, contract.contract_hash, canonical_hash(plan), request


async def test_claim_revalidates_authority_immediately_before_effect(stf_db):
    _, factory = stf_db
    run_id, execution_id, contract_hash, plan_hash, request = await seeded(factory)
    async with factory() as session:
        receipt = await StfRepository(session).claim_execution(
            execution_id=execution_id, run_id=run_id, contract_hash=contract_hash, plan_hash=plan_hash,
            tool_id="range.health.verify", parameters_hash=canonical_hash(request.parameters),
        )
        await session.commit()
    assert receipt.status == "dispatched"
    assert receipt.execution_id == execution_id


async def test_cancel_after_authorization_blocks_runtime_claim(stf_db):
    _, factory = stf_db
    run_id, execution_id, contract_hash, plan_hash, request = await seeded(factory)
    async with factory() as session:
        await StfRepository(session).revoke_run(run_id)
        await session.commit()
    async with factory() as session:
        receipt = await StfRepository(session).claim_execution(
            execution_id=execution_id, run_id=run_id, contract_hash=contract_hash, plan_hash=plan_hash,
            tool_id="range.health.verify", parameters_hash=canonical_hash(request.parameters),
        )
    assert receipt.status == "denied"
    assert "run_cancelled" in receipt.reason_codes


@pytest.mark.parametrize("field", ["contract_hash", "plan_hash", "tool_id", "parameters_hash"])
async def test_claim_rejects_changed_runtime_binding(stf_db, field):
    _, factory = stf_db
    run_id, execution_id, contract_hash, plan_hash, request = await seeded(factory)
    values = {
        "execution_id": execution_id,
        "run_id": run_id,
        "contract_hash": contract_hash,
        "plan_hash": plan_hash,
        "tool_id": "range.health.verify",
        "parameters_hash": canonical_hash(request.parameters),
    }
    values[field] = "changed"
    async with factory() as session:
        receipt = await StfRepository(session).claim_execution(**values)
    assert receipt.status == "denied"
