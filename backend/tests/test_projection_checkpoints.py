from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.projections.checkpoints import ProjectionRegressionError, load_checkpoint, save_checkpoint

pytestmark = pytest.mark.integration


@pytest.fixture
async def database():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE projection_checkpoints"))
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_projection_checkpoint_advances_monotonically(database):
    async with database() as session:
        await save_checkpoint(session, projection_name="system", position=4, state={"value": 1})
        await session.commit()
        await save_checkpoint(session, projection_name="system", position=7, state={"value": 2})
        await session.commit()

    async with database() as session:
        checkpoint = await load_checkpoint(session, "system")
        assert checkpoint is not None
        assert checkpoint.position == 7
        assert checkpoint.state_json == {"value": 2}


@pytest.mark.asyncio
async def test_projection_checkpoint_rejects_regression(database):
    async with database() as session:
        await save_checkpoint(session, projection_name="system", position=7, state={"value": 2})
        await session.commit()
        with pytest.raises(ProjectionRegressionError):
            await save_checkpoint(session, projection_name="system", position=6, state={"value": 1})
