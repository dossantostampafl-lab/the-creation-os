from __future__ import annotations

import asyncio

from loguru import logger

from app.db.session import AsyncSessionLocal
from app.knowledge.indexer import process_batch


async def run() -> None:
    while True:
        try:
            count = await process_batch(AsyncSessionLocal)
        except Exception as exc:
            logger.bind(component='knowledge_worker', error_type=type(exc).__name__).warning('knowledge consumer unavailable')
            count = 0
        await asyncio.sleep(0.1 if count else 2)

if __name__ == '__main__':
    asyncio.run(run())
