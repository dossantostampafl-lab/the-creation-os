from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from .workflows import MissionWorkflow


async def main() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "temporal:7233"))
    worker = Worker(client, task_queue="security-task-force", workflows=[MissionWorkflow])
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
