from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.models.entities import Chronicle, Universe
from app.repositories.domain import DomainRepository
from app.schemas.chronicle import ChronicleResponse, ChronicleVerifyResponse
from app.schemas.pulse import PulseResponse
from app.schemas.tree_core import UniverseResponse
from app.services.pulse import build_pulse_snapshot

router = APIRouter(tags=["creator-interface"], dependencies=[Depends(get_sovereign_creator)])


def chronicle_response(item: Chronicle) -> ChronicleResponse:
    return ChronicleResponse(
        id=item.id,
        event_id=item.event_id,
        position=item.position,
        correlation_id=item.correlation_id,
        causation_id=item.causation_id,
        actor_type=item.actor_type,
        actor_role=item.actor_role,
        actor_id=item.actor_id,
        event_type=item.event_type,
        aggregate_type=item.aggregate_type,
        aggregate_id=item.aggregate_id,
        payload_json=item.payload_json,
        payload_hash=item.payload_hash,
        previous_hash=item.previous_hash,
        created_at=item.created_at,
    )


def universe_response(item: Universe) -> UniverseResponse:
    return UniverseResponse(
        id=item.id,
        code=item.code,
        name=item.name,
        active=item.active,
        created_at=item.created_at,
    )


@router.get("/chronicles", response_model=list[ChronicleResponse])
async def list_chronicles(
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    result = await session.scalars(select(Chronicle).order_by(Chronicle.position.desc()).limit(limit))
    return [chronicle_response(item) for item in result.all()]


@router.get("/chronicles/verify", response_model=ChronicleVerifyResponse)
async def verify_chronicles(session: AsyncSession = Depends(get_session)):
    integrity = await DomainRepository(session).verify_chronicle()
    if integrity.valid:
        return ChronicleVerifyResponse(valid=True, message="Chronicle chain verified with no adulteration detected.")
    return ChronicleVerifyResponse(
        valid=False,
        message=f"Chronicle chain invalid at event {integrity.first_invalid_event_id}: {integrity.reason}",
    )


@router.get("/universes", response_model=list[UniverseResponse])
async def list_universes(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(Universe).order_by(Universe.name, Universe.code))
    return [universe_response(item) for item in result.all()]


@router.get("/pulse", response_model=PulseResponse)
async def pulse(session: AsyncSession = Depends(get_session)):
    return PulseResponse(**await build_pulse_snapshot(session))
