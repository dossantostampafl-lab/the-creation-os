from __future__ import annotations

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.projection import ProjectionCheckpoint
from app.projections.system import (
    AGENT_PROJECTION,
    MEMORY_PROJECTION,
    MISSION_PROJECTION,
    SYSTEM_PROJECTION,
    TASK_PROJECTION,
    system_snapshot,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_system_snapshot_persists_all_projection_checkpoints() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE projection_checkpoints"))

        async with factory() as session:
            snapshot = await system_snapshot(session, persist=True)
            assert snapshot["position"] >= 0

        async with factory() as session:
            checkpoints = list((await session.scalars(select(ProjectionCheckpoint))).all())
            names = {checkpoint.projection_name for checkpoint in checkpoints}
            assert names == {
                SYSTEM_PROJECTION,
                MISSION_PROJECTION,
                TASK_PROJECTION,
                AGENT_PROJECTION,
                MEMORY_PROJECTION,
            }
            assert {checkpoint.position for checkpoint in checkpoints} == {snapshot["position"]}
    finally:
        await engine.dispose()
