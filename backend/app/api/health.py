import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.alembic_utils import resolve_alembic_head
from app.db.session import get_session

router = APIRouter()


@router.get("/health/live")
async def live():
    return {"status": "live"}


@router.get("/health/ready")
async def ready(session: AsyncSession = Depends(get_session)):
    try:
        expected_revision = resolve_alembic_head()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready: could not resolve the expected Alembic migration head",
        ) from exc

    redis = Redis.from_url(settings.redis_url)
    try:
        async with asyncio.timeout(2):
            await session.execute(text("SELECT 1"))
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != expected_revision:
                raise RuntimeError(f"unexpected migration revision: {revision!r} != {expected_revision!r}")
            if not await redis.ping():
                raise RuntimeError("redis ping failed")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready") from exc
    finally:
        await redis.aclose()
    return {"status": "ready"}
