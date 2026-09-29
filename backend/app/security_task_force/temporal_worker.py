from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from app.db.session import AsyncSessionLocal

from .activities import StfActivities, StfDependencies
from .contract_store import ContractStore
from .dispatcher import TemporalDispatcher
from .gateway_client import TcpGatewayClient
from .grants import GrantStore
from .kill_switch import KillSwitch
from .ledger import DispatchLedger
from .policy import OpaClient
from .status_store import MissionStatusStore
from .workflows import MissionWorkflow

TASK_QUEUE = "security-task-force"
DISPATCH_INTERVAL_SECONDS = 2.0


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
        session_factory=AsyncSessionLocal,
    )


async def main() -> None:
    # Telemetry lines are one JSON object each; without a handler the stf logger drops them.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "temporal:7233"))
    activities = StfActivities(build_dependencies())
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=[MissionWorkflow], activities=activities.all())
    dispatcher = TemporalDispatcher(AsyncSessionLocal, client, task_queue=TASK_QUEUE)

    async def deliver_outbox() -> None:
        while True:
            try:
                await dispatcher.dispatch_once()
            except Exception:  # noqa: BLE001 - a failed pass is retried; the outbox keeps every item
                logging.getLogger("stf").exception("outbox pass failed")
            await asyncio.sleep(DISPATCH_INTERVAL_SECONDS)

    await asyncio.gather(worker.run(), deliver_outbox())


if __name__ == "__main__":
    asyncio.run(main())
