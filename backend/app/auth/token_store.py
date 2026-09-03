from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.asyncio import Redis

from app.config import settings

REFRESH_PREFIX = "auth:refresh"
LOGIN_FAILURE_PREFIX = "auth:login-failures"


@asynccontextmanager
async def _client() -> AsyncIterator[Redis]:
    redis: Redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.aclose()


def _refresh_key(subject: str, jti: str) -> str:
    return f"{REFRESH_PREFIX}:{subject}:{jti}"


async def register_refresh_token(subject: str, jti: str) -> None:
    async with _client() as redis:
        await redis.set(_refresh_key(subject, jti), "1", ex=int(settings.refresh_token_expires.total_seconds()))


async def consume_refresh_token(subject: str, jti: str) -> bool:
    """Single-use semantics: the token is valid only if the delete removed it."""
    async with _client() as redis:
        return bool(await redis.delete(_refresh_key(subject, jti)))


async def revoke_refresh_tokens(subject: str) -> int:
    async with _client() as redis:
        keys = [key async for key in redis.scan_iter(match=f"{REFRESH_PREFIX}:{subject}:*", count=100)]
        return int(await redis.delete(*keys)) if keys else 0


async def register_login_failure(username: str) -> int:
    async with _client() as redis:
        key = f"{LOGIN_FAILURE_PREFIX}:{username}"
        failures = int(await redis.incr(key))
        if failures == 1:
            await redis.expire(key, settings.login_failure_window_seconds)
        return failures


async def clear_login_failures(username: str) -> None:
    async with _client() as redis:
        await redis.delete(f"{LOGIN_FAILURE_PREFIX}:{username}")


async def login_is_blocked(username: str) -> bool:
    async with _client() as redis:
        failures = await redis.get(f"{LOGIN_FAILURE_PREFIX}:{username}")
        return failures is not None and int(failures) >= settings.login_max_failures
