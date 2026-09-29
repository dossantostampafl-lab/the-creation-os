from __future__ import annotations

import pytest

from stf_helpers import action, make


@pytest.mark.asyncio
async def test_protocol_v2_binds_run_execution_contract_plan_and_tool(tmp_path):
    activities, deps = make(tmp_path)
    request = action()
    decision = await activities.authorize_action("m1", request, None)
    assert decision["decision"] == "permit"

    # Runtime identity comes from the durable run/dispatch reservation, not from the model.
    decision.update(
        run_id="run-1",
        execution_id="exec-1",
        contract_hash="c" * 64,
        plan_hash="p" * 64,
        tool_id="range.health.verify",
    )
    await activities.dispatch_action(request, decision)

    envelope, requested = deps.gateway.calls[0]
    assert envelope["protocol_version"] == 2
    assert envelope["run_id"] == "run-1"
    assert envelope["execution_id"] == "exec-1"
    assert envelope["contract_hash"] == "c" * 64
    assert envelope["plan_hash"] == "p" * 64
    assert envelope["tool_id"] == "range.health.verify"
    assert envelope["parameters_hash"] == requested["parameters_hash"]


@pytest.mark.asyncio
async def test_protocol_v2_rejects_noncanonical_initial_capability_parameters(tmp_path):
    activities, _ = make(tmp_path)
    request = action(parameters={"path": "/", "timeout": 1.5})
    decision = await activities.authorize_action("m1", request, None)
    decision.update(
        run_id="run-1",
        execution_id="exec-1",
        contract_hash="c" * 64,
        plan_hash="p" * 64,
        tool_id="range.health.verify",
    )

    with pytest.raises(ValueError, match="canonical"):
        await activities.dispatch_action(request, decision)
