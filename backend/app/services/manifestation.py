from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.domain import DomainError
from app.core.manifestation import build_manifestation, is_valid_fingerprint
from app.models.manifestation import MissionManifestation
from app.repositories.manifestation import ManifestationRepository
from app.services.domain import NotFoundError


class ManifestationError(DomainError):
    pass


class ManifestationService:
    def __init__(self, repository: ManifestationRepository) -> None:
        self.repository = repository

    async def manifest(self, mission_id: str) -> tuple[MissionManifestation, bool]:
        mission = await self.repository.mission(mission_id, lock=True)
        if mission is None:
            await self.repository.rollback()
            raise NotFoundError("Mission not found")

        existing = await self.repository.manifestation(mission_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        try:
            decision = await self.repository.decision(mission_id)
            if decision is None:
                raise ManifestationError("MissionDecision is required before manifestation")
            if decision.decision != "APPROVED":
                raise ManifestationError("MissionDecision must be APPROVED before manifestation")
            if not is_valid_fingerprint(decision.consolidation_fingerprint):
                raise ManifestationError("MissionDecision fingerprint is invalid")

            document = build_manifestation(decision)
            item = MissionManifestation(
                mission_id=mission.id,
                decision_id=decision.id,
                manifestation_state=document.state.value,
                manifestation_payload=document.payload,
                manifestation_fingerprint=document.fingerprint,
                audit_metadata=document.audit_metadata,
            )
            await self.repository.add(item)
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.manifestation(mission_id)
            if existing is not None:
                return existing, False
            raise ManifestationError("Manifestation could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def get(self, mission_id: str) -> MissionManifestation:
        item = await self.repository.manifestation(mission_id)
        if item is None:
            raise NotFoundError("Mission manifestation not found")
        return item
