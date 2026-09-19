from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any

import redis.asyncio as redis


_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class RedisCacheStore:
    def __init__(self, url: str, *, prefix: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.prefix = prefix.rstrip(":")

    def _key(self, kind: str, key: str) -> str:
        return f"{self.prefix}:{kind}:{key}"

    async def get_exact(self, exact_key: str) -> dict[str, Any] | None:
        raw = await self.client.get(self._key("exact", exact_key))
        if raw is None:
            return None
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None

    async def set_exact(self, exact_key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        await self.client.set(
            self._key("exact", exact_key),
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            ex=max(1, ttl_seconds),
        )

    async def delete_exact(self, exact_keys: list[str]) -> None:
        if exact_keys:
            await self.client.delete(*(self._key("exact", key) for key in exact_keys))

    async def acquire_lock(self, exact_key: str, ttl_seconds: int) -> str | None:
        token = secrets.token_urlsafe(24)
        acquired = await self.client.set(
            self._key("lock", exact_key),
            token,
            ex=max(1, ttl_seconds),
            nx=True,
        )
        return token if acquired else None

    async def release_lock(self, exact_key: str, token: str) -> None:
        await self.client.eval(_RELEASE_LOCK_SCRIPT, 1, self._key("lock", exact_key), token)

    async def wait_for_exact(self, exact_key: str, wait_ms: int, poll_ms: int = 50) -> dict[str, Any] | None:
        remaining = max(0, wait_ms)
        while remaining > 0:
            payload = await self.get_exact(exact_key)
            if payload is not None:
                return payload
            interval = min(poll_ms, remaining)
            await asyncio.sleep(interval / 1000)
            remaining -= interval
        return await self.get_exact(exact_key)

    async def increment(self, metric: str, amount: int = 1) -> None:
        await self.client.hincrby(self._key("metrics", "global"), metric, amount)

    async def metrics_snapshot(self) -> dict[str, int]:
        raw = await self.client.hgetall(self._key("metrics", "global"))
        return {str(key): int(value) for key, value in raw.items()}

    async def close(self) -> None:
        await self.client.aclose()
