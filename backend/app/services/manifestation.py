from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError

from app.core.domain import DomainError, MissionStatus, require_malkuth_authorized, transition
from app.core.manifestation import build_manifestation, is_valid_fingerprint
from app.models.manifestation import MissionManifestation
from app.repositories.manifestation import ManifestationRepository
from app.services.domain import NotFoundError


class ManifestationError(DomainError):
    pass


class ManifestationService:
    def __init__(self, repository: ManifestationRepository) -> None:
        self.repository = repository

    async def manifest(
        self,
        mission_id: str,
        *,
        correlation_id: str | None = None,
        actor_id: str = "system",
        actor_role: str = "system",
        causation_id: str | None = None,
    ) -> tuple[MissionManifestation, bool]:
        correlation_id = correlation_id or str(uuid.uuid4())
        mission = await self.repository.mission(mission_id, lock=True)
        if mission is None:
            await self.repository.rollback()
            raise NotFoundError("Mission not found")

        existing = await self.repository.manifestation(mission_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        # Only gates *new* manifestation — see the matching comment in ConsolidationService.consolidate.
        require_malkuth_authorized(mission.status)

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
            # Terminal status transition, same locked row/transaction as the manifestation
            # insert above: a concurrent loser sees status already MANIFESTED and no-ops.
            if MissionStatus(mission.status) != MissionStatus.MANIFESTED:
                mission.status = transition("mission", MissionStatus(mission.status), MissionStatus.MANIFESTED)
            await self.repository.add_event(
                "mission_manifested", mission.id, actor_id, actor_role, correlation_id,
                {"manifestation_id": item.id, "decision_id": decision.id}, causation_id=causation_id,
            )
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
