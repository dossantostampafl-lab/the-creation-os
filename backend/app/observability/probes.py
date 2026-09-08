from __future__ import annotations

import time
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

PROBE_TIMEOUT_SECONDS = 2


async def database_probe(session: AsyncSession) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    return {"available": True, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "migration": revision}


async def redis_probes() -> tuple[dict[str, Any], dict[str, Any]]:
    redis: Redis = Redis.from_url(settings.redis_url, socket_timeout=PROBE_TIMEOUT_SECONDS,
                                  socket_connect_timeout=PROBE_TIMEOUT_SECONDS)
    started = time.perf_counter()
    try:
        await redis.ping()
        streams = {}
        async for key in redis.scan_iter(count=100, _type="STREAM"):
            name = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            streams[name] = await redis.xlen(name)
    except Exception as exc:
        return {"available": False, "error": str(exc)}, {"available": False, "streams": {}}
    finally:
        await redis.aclose()
    return ({"available": True, "latency_ms": round((time.perf_counter() - started) * 1000, 2)},
            {"available": True, "streams": streams})
