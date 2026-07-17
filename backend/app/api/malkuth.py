from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.db.session import get_session
from app.models.manifestation import MissionManifestation
from app.repositories.manifestation import ManifestationRepository
from app.schemas.manifestation import MissionManifestationResponse
from app.services.manifestation import ManifestationService

router = APIRouter(tags=["malkuth"], dependencies=[Depends(get_sovereign_creator)])


def service(session: AsyncSession = Depends(get_session)) -> ManifestationService:
    return ManifestationService(ManifestationRepository(session))


def manifestation_response(item: MissionManifestation) -> MissionManifestationResponse:
    return MissionManifestationResponse(
        id=item.id,
        mission_id=item.mission_id,
        decision_id=item.decision_id,
        manifestation_state=item.manifestation_state,
        manifestation_payload=item.manifestation_payload,
        manifestation_fingerprint=item.manifestation_fingerprint,
        audit_metadata=item.audit_metadata,
        created_at=item.created_at,
        manifested_at=item.manifested_at,
    )


@router.post(
    "/malkuth/missions/{mission_id}/manifest",
    response_model=MissionManifestationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def manifest_mission(
    mission_id: uuid.UUID,
    response: Response,
    manifestation_service: ManifestationService = Depends(service),
):
    item, created = await manifestation_service.manifest(str(mission_id))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return manifestation_response(item)


@router.get(
    "/malkuth/missions/{mission_id}/manifestation",
    response_model=MissionManifestationResponse,
)
async def get_mission_manifestation(
    mission_id: uuid.UUID,
    manifestation_service: ManifestationService = Depends(service),
):
    return manifestation_response(await manifestation_service.get(str(mission_id)))
