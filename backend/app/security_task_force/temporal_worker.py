from __future__ import annotations

import asyncio
import os
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import StfActivities, StfDependencies
from .contract_store import ContractStore
from .gateway_client import TcpGatewayClient
from .grants import GrantStore
from .kill_switch import KillSwitch
from .ledger import DispatchLedger
from .policy import OpaClient
from .status_store import MissionStatusStore
from .workflows import MissionWorkflow

TASK_QUEUE = "security-task-force"


def build_dependencies() -> StfDependencies:
    key = os.environ.get("STF_GATEWAY_SIGNING_KEY", "").encode()
    if len(key) < 32:
        raise RuntimeError("STF_GATEWAY_SIGNING_KEY (32+ characters) is required")
    state = Path(os.environ.get("STF_STATE_DIR", "/var/lib/creation/stf"))
    return StfDependencies(
        contracts=ContractStore(state / "contracts.json"),
        grants=GrantStore(state / "grants.json"),
        kill_switch=KillSwitch(state / "kill.json"),
        ledger=DispatchLedger(state / "ledger.json"),
        gateway=TcpGatewayClient(),
        signing_key=key,
        statuses=MissionStatusStore(state / "status.json"),
        policy=OpaClient(os.environ.get("OPA_URL", "http://stf-opa:8181")),
    )


async def main() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "temporal:7233"))
    activities = StfActivities(build_dependencies())
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=[MissionWorkflow], activities=activities.all())
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
