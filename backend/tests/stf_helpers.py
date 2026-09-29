from app.security_task_force.activities import StfActivities, StfDependencies
from app.security_task_force.contract_store import ContractStore
from app.security_task_force.gateway_client import GatewayUnavailable
from app.security_task_force.grants import GrantStore
from app.security_task_force.kill_switch import KillSwitch
from app.security_task_force.ledger import DispatchLedger
from app.security_task_force.mission_compiler import compile_verified_contract

RANGE = "cyber_range:lab-a"
CANDIDATE = {
    "mission_id": "m1", "creator_id": "c1", "success_criteria": ["evidence"], "authorized_targets": ["juice-shop"],
    "allowed_action_classes": ["validate"], "risk_ceiling": "R4",
}


def action(**overrides):
    data = dict(action_id="a1", mission_id="m1", mission_version=1, task_id="t1", actor="agent:red",
                target_id="juice-shop", environment_id=RANGE, capability="range.health.verify",
                action_class="validate", risk_class="R2", idempotency_key="k1", parameters={"path": "/"})
    data.update(overrides)
    return data


class FakeGateway:
    def __init__(self, answer=None, fail=False):
        # The positive double says outright that the work ran and names it; production never assumes this.
        default = {"decision": "permit", "status": "executed", "execution_id": "exec-1", "reasons": []}
        self.calls, self.controls, self.answer, self.fail = [], [], answer or default, fail

    async def execute(self, envelope, requested):
        if self.fail:
            raise GatewayUnavailable("down")
        self.calls.append((envelope, requested))
        return self.answer

    async def control(self, message):
        self.controls.append(message)
        return {"decision": "ok"}


def make(tmp_path, gateway=None, policy=None, verify=lambda mission_id: True):
    contracts = ContractStore(tmp_path / "contracts.json")
    contracts.put(compile_verified_contract(intent="validate", candidate=CANDIDATE, authorized_environments=[RANGE]))
    deps = StfDependencies(
        contracts=contracts, grants=GrantStore(tmp_path / "grants.json"), kill_switch=KillSwitch(tmp_path / "kill.json"),
        ledger=DispatchLedger(tmp_path / "ledger.json"), gateway=gateway or FakeGateway(), signing_key=b"k" * 40, policy=policy, verify=verify,
    )
    return StfActivities(deps), deps
