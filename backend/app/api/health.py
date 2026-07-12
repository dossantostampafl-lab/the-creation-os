import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session

router = APIRouter()


@router.get("/health/live")
async def live():
    return {"status": "live"}


@router.get("/health/ready")
async def ready(session: AsyncSession = Depends(get_session)):
    redis = Redis.from_url(settings.redis_url)
    try:
        async with asyncio.timeout(2):
            await session.execute(text("SELECT 1"))
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "0003_stabilization":
                raise RuntimeError("unexpected migration revision")
            if not await redis.ping():
                raise RuntimeError("redis ping failed")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready") from exc
    finally:
        await redis.aclose()
    return {"status": "ready"}
