from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import actor
from app.config import settings
from app.core.domain import Actor, require_creator
from app.db.session import get_session
from app.projections.opportunity import build_creator_opportunity_projection

router = APIRouter()


@router.get("/opportunities/projection")
async def opportunity_projection(
    a: Actor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    require_creator(a, "view opportunity economic projection")
    return await build_creator_opportunity_projection(
        session,
        creator_id=a.id,
        currency=settings.economic_currency,
    )
