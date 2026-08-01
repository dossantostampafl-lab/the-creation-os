from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError

from app.core.decision import evaluate_decision
from app.core.domain import DomainError, require_malkuth_authorized
from app.models.decision import MissionDecision
from app.repositories.decision import DecisionRepository
from app.services.domain import NotFoundError


class DecisionError(DomainError):
    pass


class DecisionService:
    def __init__(self, repository: DecisionRepository) -> None:
        self.repository = repository

    async def decide(
        self,
        mission_id: str,
        *,
        correlation_id: str | None = None,
        actor_id: str = "system",
        actor_role: str = "system",
        causation_id: str | None = None,
    ) -> tuple[MissionDecision, bool]:
        correlation_id = correlation_id or str(uuid.uuid4())
        mission = await self.repository.mission(mission_id, lock=True)
        if mission is None:
            await self.repository.rollback()
            raise NotFoundError("Mission not found")

        existing = await self.repository.decision(mission_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        # Only gates *new* decisions — see the matching comment in ConsolidationService.consolidate.
        require_malkuth_authorized(mission.status)

        try:
            consolidation = await self.repository.consolidation(mission_id)
            document = evaluate_decision(mission.id, consolidation)
            item = MissionDecision(
                mission_id=mission.id,
                consolidation_id=consolidation.id if consolidation is not None else None,
                decision=document.decision.value,
                justification_json=document.justification,
                consolidation_fingerprint=document.consolidation_fingerprint,
            )
            await self.repository.add(item)
            await self.repository.add_event(
                "mission_decided", mission.id, actor_id, actor_role, correlation_id,
                {"decision_id": item.id, "decision": item.decision}, causation_id=causation_id,
            )
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.decision(mission_id)
            if existing is not None:
                return existing, False
            raise DecisionError("Decision could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def get(self, mission_id: str) -> MissionDecision:
        item = await self.repository.decision(mission_id)
        if item is None:
            raise NotFoundError("Mission decision not found")
        return item
