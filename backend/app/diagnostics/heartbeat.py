from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.session import AsyncSessionLocal


class ServiceHeartbeat(Base):
    __tablename__ = 'service_heartbeats'
    service: Mapped[str] = mapped_column(String(64), primary_key=True)
    boot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lease_owner: Mapped[str] = mapped_column(String(36))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


async def supervised(service: str, run: Callable[[], Awaitable[None]]) -> None:
    from app.config import settings
    from app.observability.telemetry import configure_telemetry
    configure_telemetry(service)
    if not settings.deus_diagnostics_enabled:
        await run()
        return
    boot_id = str(uuid.uuid4())
    async def heartbeat():
        while True:
            try:
                now = datetime.now(timezone.utc)
                async with asyncio.timeout(2), AsyncSessionLocal() as session:
                    await session.execute(insert(ServiceHeartbeat).values(service=service,
                        boot_id=boot_id, lease_owner=boot_id, observed_at=now,
                        valid_until=now+timedelta(seconds=45), metrics={}).on_conflict_do_update(
                            index_elements=['service','boot_id'], set_={'observed_at':now,'valid_until':now+timedelta(seconds=45)}))
                    await session.commit()
            except Exception as exc:
                logger.bind(component='heartbeat', error_type=type(exc).__name__).warning('service heartbeat unavailable')
            await asyncio.sleep(15)
    task = asyncio.create_task(heartbeat())
    try:
        await run()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
