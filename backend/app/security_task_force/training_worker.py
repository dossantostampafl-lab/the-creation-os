from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.diagnostics.heartbeat import supervised
from app.models.entities import Creator
from app.security_task_force.training import AutomaticRangeTraining


async def creator_scope() -> str | None:
    async with AsyncSessionLocal() as session:
        if settings.sovereign_creator_id:
            return await session.scalar(
                select(Creator.id).where(
                    Creator.id == settings.sovereign_creator_id,
                    Creator.is_active.is_(True),
                )
            )
        ids = list(
            await session.scalars(
                select(Creator.id).where(Creator.is_active.is_(True)).limit(2)
            )
        )
        return ids[0] if len(ids) == 1 else None


async def run() -> None:
    if not settings.stf_auto_training_enabled:
        logger.info("STF automatic Cyber Range training disabled")
        return

    coordinator = AutomaticRangeTraining(AsyncSessionLocal)
    while True:
        try:
            creator_id = await creator_scope()
            if creator_id is None:
                logger.warning("STF training has no unambiguous active Creator")
            else:
                report = await coordinator.run_once(creator_id)
                logger.bind(component="stf-training", **report).info(
                    "automatic Cyber Range training cycle"
                )
        except Exception as exc:
            logger.bind(
                component="stf-training",
                error_type=type(exc).__name__,
            ).warning("automatic Cyber Range training cycle unavailable")
        await asyncio.sleep(settings.stf_auto_training_cycle_seconds)


if __name__ == "__main__":
    asyncio.run(supervised("stf-training-worker", run))
