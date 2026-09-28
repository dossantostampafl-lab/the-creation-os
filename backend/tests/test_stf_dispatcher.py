"""The outbox-to-Temporal dispatcher against a guarded database and a scripted Temporal client.

The real workflow behavior (approval gating, cancel, empty plan) is in test_stf_workflow.py on the Temporal
test server. Here the client is a double so crashes and duplicates can be forced exactly.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.models.entities import Creator
from app.security_task_force.dispatcher import TemporalDispatcher

PAYLOAD = {"run_id": "r1", "workflow_id": "stf:r1", "mission_id": "m1", "mission_version": 1, "plan_hash": "h1",
           "plan": [{"action_id": "a1"}]}


class Description:
    def __init__(self, memo):
        self._memo = memo

    async def memo_value(self, key, default=None):
        return self._memo.get(key, default)


class Handle:
    def __init__(self, client, workflow_id):
        self.client, self.workflow_id = client, workflow_id

    async def describe(self):
        return Description(self.client.workflows[self.workflow_id]["memo"])

    async def signal(self, name, *args):
        if self.workflow_id not in self.client.workflows:
            raise RuntimeError("workflow not found")
        self.client.signals.append((self.workflow_id, name, args))


class FakeClient:
    def __init__(self):
        self.workflows, self.signals, self.crash_after_start = {}, [], False

    async def start_workflow(self, workflow, plan, *, id, task_queue, memo=None, **kwargs):
        if id in self.workflows:
            raise WorkflowAlreadyStartedError(id, "MissionWorkflow")
        self.workflows[id] = {"plan": plan, "memo": memo, "policy": kwargs}
        if self.crash_after_start:
            self.crash_after_start = False
            raise ConnectionError("response lost after the server accepted the start")

    def get_workflow_handle(self, workflow_id):
        return Handle(self, workflow_id)


async def _outbox(factory, *items):
    from app.security_task_force.repository import StfRepository

    async with factory() as session:
        repository = StfRepository(session)
        for destination, payload in items:
            await repository.add_outbox(destination, payload)
        await session.commit()


async def _status(factory):
    async with factory() as session:
        rows = await session.execute(text("SELECT destination, status FROM stf_outbox ORDER BY created_at"))
        return [tuple(row) for row in rows]


async def _expire(factory):
    async with factory() as session:
        await session.execute(text("UPDATE stf_outbox SET lease_expires_at = now() - interval '1 second' WHERE status = 'leased'"))
        await session.commit()


async def test_crash_after_start_does_not_duplicate(stf_db):
    _, factory = stf_db
    client = FakeClient()
    await _outbox(factory, ("start", PAYLOAD))
    dispatcher = TemporalDispatcher(factory, client)
    client.crash_after_start = True
    assert await dispatcher.dispatch_once() == 0  # uncertain: not acknowledged
    assert await _status(factory) == [("start", "leased")]
    await _expire(factory)
    assert await dispatcher.dispatch_once() == 1  # the retry finds the same workflow and confirms its identity
    assert len(client.workflows) == 1 and await _status(factory) == [("start", "acked")]
    assert client.workflows["stf:r1"]["policy"]["id_reuse_policy"].name == "REJECT_DUPLICATE"


async def test_a_workflow_with_another_plan_is_never_adopted(stf_db):
    _, factory = stf_db
    client = FakeClient()
    client.workflows["stf:r1"] = {"memo": {"run_id": "r1", "plan_hash": "someone-else"}}
    await _outbox(factory, ("start", PAYLOAD))
    assert await TemporalDispatcher(factory, client).dispatch_once() == 0
    assert await _status(factory) == [("start", "dead")]


async def test_signals_wait_for_the_workflow_and_are_delivered_after_it_starts(stf_db):
    _, factory = stf_db
    client = FakeClient()
    signal = {"run_id": "r1", "workflow_id": "stf:r1", "signal": "cancel", "reason": "stop"}
    await _outbox(factory, ("signal", signal))
    dispatcher = TemporalDispatcher(factory, client)
    assert await dispatcher.dispatch_once() == 0 and client.signals == []  # nothing to signal yet, nothing lost
    await _outbox(factory, ("start", PAYLOAD))
    await _expire(factory)
    assert await dispatcher.dispatch_once() == 2  # start first, then the signal in the same pass
    assert client.signals == [("stf:r1", "cancel", ("stop",))]


async def test_an_item_that_keeps_failing_is_marked_dead_not_retried_forever(stf_db):
    _, factory = stf_db
    client = FakeClient()
    await _outbox(factory, ("signal", {"run_id": "r1", "workflow_id": "stf:gone", "signal": "approve", "approval_id": "x"}))
    dispatcher = TemporalDispatcher(factory, client, max_attempts=2)
    for _ in range(2):
        await dispatcher.dispatch_once()
        await _expire(factory)
    assert await _status(factory) == [("signal", "dead")]


async def _seed_run(factory, *, decision="approve", expires=timedelta(minutes=5), parameters=None):
    from app.security_task_force.canonicalize import canonical_hash
    from app.security_task_force.repository import StfRepository

    creator_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
    action = {"action_id": "a1", "parameters": {"path": "/"}}
    async with factory() as session:
        session.add(Creator(id=creator_id, username=f"c-{creator_id[:8]}", password_hash="x", is_active=True))
        await session.flush()
        repository = StfRepository(session)
        await repository.create_run(creator_id=creator_id, run_id=run_id, mission_id="m1", mission_version=1,
                                    request_key="k", request_hash="h" * 64, plan_hash="p" * 64, plan=[action])
        approval = await repository.add_approval(
            creator_id=creator_id, run_id=run_id, action_id="a1",
            parameters_hash=canonical_hash(parameters or action["parameters"]),
            expires_at=datetime.now(timezone.utc) + expires, decision=decision)
        await session.commit()
    return run_id, approval.id, action


@pytest.mark.parametrize("case,ok", [("valid", True), ("denied", False), ("expired", False), ("other_params", False),
                                    ("other_action", False), ("unknown_id", False)])
async def test_an_approval_unblocks_only_the_exact_action_it_was_given_for(stf_db, case, ok):
    from app.security_task_force.repository import StfRepository

    _, factory = stf_db
    kwargs = {"denied": {"decision": "deny"}, "expired": {"expires": timedelta(seconds=-1)},
              "other_params": {"parameters": {"path": "/x"}}}.get(case, {})
    run_id, approval_id, action = await _seed_run(factory, **kwargs)
    if case == "other_action":
        action = {**action, "action_id": "a2"}
    if case == "unknown_id":
        approval_id = str(uuid.uuid4())
    async with factory() as session:
        assert await StfRepository(session).approval_matches(approval_id, run_id, action) is ok


async def test_run_states_never_reopen_a_terminal_run_or_resurrect_a_cancelled_one(stf_db):
    from app.security_task_force.repository import StfRepository

    _, factory = stf_db
    run_id, _, _ = await _seed_run(factory)
    async with factory() as session:
        repository = StfRepository(session)
        assert await repository.set_run_state(run_id, "RUNNING")
        await repository.revoke_run(run_id)
        assert not await repository.set_run_state(run_id, "RUNNING")  # cancel is not undone by a late worker
        assert await repository.set_run_state(run_id, "ABORTED")
        assert not await repository.set_run_state(run_id, "RUNNING")  # terminal stays terminal
        await session.commit()
