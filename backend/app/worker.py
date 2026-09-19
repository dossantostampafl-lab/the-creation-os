from __future__ import annotations

import asyncio
import uuid

from loguru import logger
from sqlalchemy import select

from app.capabilities.gateway import CapabilityGateway
from app.capabilities.proto import ProtoCapabilityAdapter
from app.capabilities.runtime import CapabilityRuntime
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.inference.bootstrap import build_model_router
from app.kernel.agent_runtime import AgentRuntime
from app.kernel.completion_engine import MissionCompletionEngine
from app.kernel.reconciler import ExecutionReconciler
from app.kernel.supervisor import MissionRuntimeSupervisor
from app.models.entities import Mission
from app.projections.refresher import ProjectionRefresher

POLL_INTERVAL_SECONDS = 1.0


def build_capability_gateway() -> CapabilityGateway:
    gateway = CapabilityGateway()
    if settings.proto_bridge_configured:
        assert settings.proto_base_url is not None
        assert settings.proto_creation_shared_secret is not None
        gateway.register(
            ProtoCapabilityAdapter(
                base_url=settings.proto_base_url,
                shared_secret=settings.proto_creation_shared_secret.get_secret_value(),
                timeout_seconds=settings.proto_timeout_seconds,
            )
        )
    return gateway


async def run_worker() -> None:
    if settings.llm_provider.strip().lower() == "fake":
        if settings.app_env == "production":
            raise RuntimeError("fake inference provider is forbidden for the production worker")
        logger.warning("worker running idle because LLM_PROVIDER=fake outside production")
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    router = build_model_router()
    capability_gateway = build_capability_gateway()
    capability_runtime = CapabilityRuntime(AsyncSessionLocal, capability_gateway)
    completion_engine = MissionCompletionEngine(AsyncSessionLocal)
    runtime = AgentRuntime(
        AsyncSessionLocal,
        router,
        capability_runtime=capability_runtime,
        completion_engine=completion_engine,
    )
    supervisor = MissionRuntimeSupervisor(AsyncSessionLocal)
    reconciler = ExecutionReconciler(AsyncSessionLocal)
    projection_refresher = ProjectionRefresher(AsyncSessionLocal)

    startup_correlation_id = str(uuid.uuid4())
    reconciled = await reconciler.reconcile(startup_correlation_id)
    logger.bind(**reconciled).info("execution reconciliation complete")
    await projection_refresher.refresh_if_needed()

    while True:
        async with AsyncSessionLocal() as session:
            missions = list((await session.scalars(
                select(Mission)
                .where(Mission.status.in_({"distributed", "executing"}))
                .order_by(Mission.created_at, Mission.id)
            )).all())
            mission_context = [
                (
                    mission.id,
                    mission.status,
                    str((mission.authorization_json or {}).get("correlation_id") or uuid.uuid4()),
                )
                for mission in missions
            ]

        did_work = False
        for mission_id, status, correlation_id in mission_context:
            if status == "distributed":
                did_work = await supervisor.start_execution(mission_id, correlation_id) or did_work
            ran_task = await runtime.run_next(mission_id, correlation_id)
            did_work = ran_task or did_work
            if not ran_task:
                target = await completion_engine.evaluate(mission_id, correlation_id)
                did_work = target is not None or did_work

        projected = await projection_refresher.refresh_if_needed()
        did_work = projected or did_work
        if not did_work:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("worker stopped")


if __name__ == "__main__":
    main()
