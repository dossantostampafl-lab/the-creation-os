from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.entities import Chronicle
from app.projections.checkpoints import load_checkpoint
from app.projections.system import SYSTEM_PROJECTION, system_snapshot


def needs_refresh(*, head: int, checkpoint: int | None) -> bool:
    return checkpoint is None or checkpoint != head


class ProjectionRefresher:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def refresh_if_needed(self) -> bool:
        async with self.session_factory() as session:
            head = int(await session.scalar(select(func.max(Chronicle.position))) or 0)
            checkpoint = await load_checkpoint(session, SYSTEM_PROJECTION)
            checkpoint_position = checkpoint.position if checkpoint is not None else None
            if not needs_refresh(head=head, checkpoint=checkpoint_position):
                return False
            await system_snapshot(session, persist=True)
            return True
