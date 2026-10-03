from __future__ import annotations

import asyncio
import time
from pathlib import Path

from loguru import logger

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.diagnostics.heartbeat import supervised
from app.diagnostics.worker import creator_scope
from app.knowledge.contracts import Scope
from app.knowledge.indexer import process_batch
from app.knowledge.obsidian import ObsidianExporter


async def run() -> None:
    last_export = 0.0
    while True:
        try:
            count = await process_batch(AsyncSessionLocal)
        except Exception as exc:
            logger.bind(component='knowledge_worker', error_type=type(exc).__name__).warning('knowledge consumer unavailable')
            count = 0
        if settings.deus_obsidian_export_enabled and time.monotonic() - last_export >= 30:
            try:
                creator_id = await creator_scope()
                if creator_id:
                    await ObsidianExporter(AsyncSessionLocal, Path(settings.deus_obsidian_root)).export(Scope(creator_id=creator_id))
                last_export = time.monotonic()
            except Exception as exc:
                logger.bind(component='obsidian_export', error_type=type(exc).__name__).warning('export unavailable; canonical memory remains in PostgreSQL')
        await asyncio.sleep(0.1 if count else 2)

if __name__ == '__main__':
    asyncio.run(supervised('knowledge-worker', run))
