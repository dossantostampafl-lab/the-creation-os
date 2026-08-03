from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import settings


class LoginRateLimiter:
    """Fixed-window counter in Redis, keyed by (source IP, attempted
    username) — reuses the same Redis instance the dispatch queue already
    depends on (settings.redis_url), no new infrastructure. Fixed-window
    chosen deliberately over a sliding-window log: this is a single-Creator
    system, the goal is friction against automated password guessing, not
    precise throughput control at a window boundary — the one real
    weakness of fixed-window (a burst straddling two windows can allow up
    to ~2x the configured limit in the worst case) doesn't matter at this
    scale, and a sliding-window log would need to store a timestamp per
    attempt instead of one integer, for no benefit this system needs.

    A successful login does not count against the limit, and clears any
    prior failed-attempt count for that key: this is about deterring
    automated guessing, not penalizing a legitimate Creator who mistyped
    their password once or twice before getting it right. Call check()
    before attempting the real login, then record_failure() or reset()
    depending on the outcome.
    """

    def __init__(self, redis: Redis, *, max_attempts: int, window_seconds: int) -> None:
        self.redis = redis
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def _key(self, ip: str, username: str) -> str:
        return f"login_rate_limit:{ip}:{username}"

    async def check(self, ip: str, username: str) -> None:
        current = await self.redis.get(self._key(ip, username))
        if current is not None and int(current) >= self.max_attempts:
            # Deliberately generic: no attempt count, no remaining-time hint
            # — nothing that helps an attacker calibrate their next request.
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    async def record_failure(self, ip: str, username: str) -> None:
        key = self._key(ip, username)
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, self.window_seconds)

    async def reset(self, ip: str, username: str) -> None:
        await self.redis.delete(self._key(ip, username))


async def get_login_rate_limiter() -> AsyncGenerator[LoginRateLimiter, None]:
    redis = Redis.from_url(settings.redis_url)
    try:
        yield LoginRateLimiter(
            redis,
            max_attempts=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )
    finally:
        await redis.aclose()
