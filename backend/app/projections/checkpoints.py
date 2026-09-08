from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projection import ProjectionCheckpoint


class ProjectionRegressionError(ValueError):
    pass


def projection_lag(*, head: int, checkpoint: int) -> int:
    if head < 0 or checkpoint < 0:
        raise ValueError("projection positions must be non-negative")
    if checkpoint > head:
        raise ValueError("projection checkpoint cannot be ahead of Chronicle head")
    return head - checkpoint


async def load_checkpoint(session: AsyncSession, projection_name: str) -> ProjectionCheckpoint | None:
    return await session.get(ProjectionCheckpoint, projection_name)


async def save_checkpoint(
    session: AsyncSession,
    *,
    projection_name: str,
    position: int,
    state: dict[str, Any],
) -> ProjectionCheckpoint:
    if position < 0:
        raise ValueError("projection position must be non-negative")

    checkpoint = await session.get(ProjectionCheckpoint, projection_name, with_for_update=True)
    if checkpoint is None:
        checkpoint = ProjectionCheckpoint(
            projection_name=projection_name,
            position=position,
            state_json=state,
        )
        session.add(checkpoint)
        await session.flush()
        return checkpoint

    if position < checkpoint.position:
        raise ProjectionRegressionError(
            f"projection {projection_name!r} cannot move backward from {checkpoint.position} to {position}"
        )

    checkpoint.position = position
    checkpoint.state_json = state
    checkpoint.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return checkpoint
