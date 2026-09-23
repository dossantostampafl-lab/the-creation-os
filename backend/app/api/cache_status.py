from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import actor
from app.cache.status import CacheStatusSnapshot, configured_cache_status
from app.core.domain import Actor

router = APIRouter(tags=["cache-status"])


@router.get("/system/cache", response_model=CacheStatusSnapshot)
async def get_cache_status(_: Actor = Depends(actor)) -> CacheStatusSnapshot:
    return await configured_cache_status()
