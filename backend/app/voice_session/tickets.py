from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.asyncio import Redis

from app.config import settings

VOICE_TICKET_PREFIX = "voice:session-ticket"


@asynccontextmanager
async def _client() -> AsyncIterator[Redis]:
    redis: Redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.aclose()


def _ticket_key(ticket: str) -> str:
    return f"{VOICE_TICKET_PREFIX}:{ticket}"


async def issue_voice_ticket(creator_id: str) -> str:
    ticket = secrets.token_urlsafe(32)
    async with _client() as redis:
        await redis.set(
            _ticket_key(ticket),
            creator_id,
            ex=settings.voice_session_ticket_ttl_seconds,
        )
    return ticket


async def consume_voice_ticket(ticket: str) -> str | None:
    if not ticket:
        return None
    async with _client() as redis:
        value = await redis.getdel(_ticket_key(ticket))
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
