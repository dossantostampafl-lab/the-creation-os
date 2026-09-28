"""Workflow behavior on the Temporal time-skipping test server.

The server binary is downloaded by the SDK. Where that is impossible (no network) the tests skip,
unless STF_REQUIRE_TEMPORAL=1, which CI sets so a skip can never pass as evidence.
"""

import os
import uuid

import pytest
from stf_helpers import action, make
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.security_task_force.activities import StfActivities
from app.security_task_force.workflows import MissionWorkflow


@pytest.fixture
async def env():
    try:
        environment = await WorkflowEnvironment.start_time_skipping()
    except RuntimeError as error:
        if os.environ.get("STF_REQUIRE_TEMPORAL") == "1":
            raise
        pytest.skip(f"Temporal test server unavailable: {error}")
    yield environment
    await environment.shutdown()


async def run_plan(env, activities: StfActivities, plan, *, signals=None):
    client: Client = env.client
    queue = f"stf-{uuid.uuid4()}"
    async with Worker(client, task_queue=queue, workflows=[MissionWorkflow], activities=activities.all()):
        handle = await client.start_workflow(MissionWorkflow.run, plan, id=f"wf-{uuid.uuid4()}", task_queue=queue)
        for name, value in signals or []:
            await handle.signal(name, value)
        return await handle.result(), handle


async def test_permitted_plan_completes_and_dispatches_once(env, tmp_path):
    activities, deps = make(tmp_path)
    result, _ = await run_plan(env, activities, {"mission_id": "m1", "actions": [action()]})
    assert result == "COMPLETED" and len(deps.gateway.calls) == 1
    assert [state for _, state in deps.states] == ["RUNNING", "VERIFYING", "COMPLETED"]


async def test_denied_action_aborts_and_revokes_grants(env, tmp_path):
    activities, deps = make(tmp_path)
    plan = {"mission_id": "m1", "actions": [action(environment_id="real:prod-a")]}
    result, _ = await run_plan(env, activities, plan)
    assert result == "ABORTED" and deps.gateway.calls == [] and not deps.kill_switch.dispatch_allowed("m1")


async def test_r3_waits_for_creator_approval_then_runs(env, tmp_path):
    activities, deps = make(tmp_path)
    plan = {"mission_id": "m1", "actions": [action(risk_class="R3")]}
    result, _ = await run_plan(env, activities, plan, signals=[("approve", "approval:1")])
    assert result == "COMPLETED" and len(deps.gateway.calls) == 1
    assert "AWAITING_CREATOR" in [state for _, state in deps.states]


async def test_r3_without_approval_times_out_and_aborts(env, tmp_path):
    activities, deps = make(tmp_path)
    plan = {"mission_id": "m1", "actions": [action(risk_class="R3")], "approval_timeout_seconds": 60}
    result, _ = await run_plan(env, activities, plan)
    assert result == "ABORTED" and deps.gateway.calls == []


async def test_cancel_signal_revokes_and_prevents_dispatch(env, tmp_path):
    activities, deps = make(tmp_path)
    plan = {"mission_id": "m1", "actions": [action(risk_class="R3")]}
    result, _ = await run_plan(env, activities, plan, signals=[("cancel", "creator stopped it")])
    assert result == "ABORTED" and deps.gateway.calls == [] and not deps.kill_switch.dispatch_allowed("m1")


async def test_failed_verification_aborts(env, tmp_path):
    activities, deps = make(tmp_path)
    deps.verify = lambda mission_id: False
    result, _ = await run_plan(env, activities, {"mission_id": "m1", "actions": [action()]})
    assert result == "ABORTED"
