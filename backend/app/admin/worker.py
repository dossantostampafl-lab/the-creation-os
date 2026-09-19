from __future__ import annotations

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.dispatch import Worker
from app.models.entities import Capability
from app.services.workers import credential_hash

SYSTEM_WORKER_UUID = "00000000-0000-0000-0000-000000000001"
SYSTEM_WORKER_NAME = "system-worker"
SYSTEM_WORKER_VERSION = "1.0"
# Every capability this single worker process must be able to lease. The dispatch
# lease query restricts acquisition to the calling Worker's own capability_ids
# (WorkerService.claim -> DispatchService.lease, app/services/workers.py), so a
# capability missing from this list would never be claimed even with a matching
# Agent and a registered handler. See docs/AUDIT_v0.5.md section 10, decision 4.
SYSTEM_WORKER_CAPABILITIES = ["planning", "knowledge_research", "engineering_design", "security_review"]


async def restore_configured_worker() -> int:
    """Provision the single bootstrap Worker's credential from the configured secret.

    Mirrors app.admin.creator.restore_configured_creator: idempotent, stores only the
    credential hash, never the plaintext, and is a no-op when no credential is configured
    (deployments that don't run the worker don't need this secret at all).
    """
    if settings.worker_credential is None:
        print(json.dumps({"restored": False, "reason": "worker_credential_not_configured"}))
        return 0

    token = settings.worker_credential.get_secret_value()

    async with AsyncSessionLocal() as session:
        capabilities = []
        for name in SYSTEM_WORKER_CAPABILITIES:
            capability = await session.scalar(select(Capability).where(Capability.name == name))
            if capability is None:
                capability = Capability(name=name, description=f"Deterministic {name} capability")
                session.add(capability)
                await session.flush()
            capabilities.append(capability)

        worker = await session.scalar(
            select(Worker).options(selectinload(Worker.capabilities)).where(Worker.worker_uuid == SYSTEM_WORKER_UUID)
        )
        if worker is None:
            session.add(
                Worker(
                    worker_uuid=SYSTEM_WORKER_UUID,
                    worker_name=SYSTEM_WORKER_NAME,
                    version=SYSTEM_WORKER_VERSION,
                    credential_hash=credential_hash(token),
                    status="registered",
                    capabilities=capabilities,
                )
            )
            await session.commit()
            print(json.dumps({"restored": True, "reason": "system_worker_created"}))
            return 0

        worker.credential_hash = credential_hash(token)
        worker.version = SYSTEM_WORKER_VERSION
        for capability in capabilities:
            if capability not in worker.capabilities:
                worker.capabilities.append(capability)
        if worker.status == "retired":
            worker.status = "registered"
        await session.commit()
        print(json.dumps({"restored": True, "reason": "system_worker_credential_updated"}))
        return 0


def main() -> None:
    raise SystemExit(asyncio.run(restore_configured_worker()))


if __name__ == "__main__":
    main()
