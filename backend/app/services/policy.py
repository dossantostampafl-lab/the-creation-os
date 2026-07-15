from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.domain import DomainError
from app.core.policy import build_decision_explanation
from app.models.policy import MissionDecisionReasoning
from app.repositories.policy import PolicyRepository
from app.services.domain import NotFoundError


class PolicyError(DomainError):
    pass


class PolicyService:
    def __init__(self, repository: PolicyRepository) -> None:
        self.repository = repository

    async def evaluate(self, mission_id: str) -> tuple[MissionDecisionReasoning, bool]:
        mission = await self.repository.mission(mission_id, lock=True)
        if mission is None:
            await self.repository.rollback()
            raise NotFoundError("Mission not found")

        decision = await self.repository.decision(mission_id)
        if decision is None:
            await self.repository.rollback()
            raise NotFoundError("Mission decision not found")

        existing = await self.repository.reasoning_for_decision(decision.id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        try:
            consolidation = await self.repository.consolidation(decision)
            active_decision_count = await self.repository.active_decision_count(mission_id)
            document = build_decision_explanation(mission.id, decision, consolidation, active_decision_count)
            item = MissionDecisionReasoning(
                decision_id=decision.id,
                policy_version=document.policy_version,
                rules_applied=document.rules_applied,
                consistency_summary=document.consistency_summary,
                completeness_summary=document.completeness_summary,
                explanation_payload=document.explanation_payload,
                fingerprint=document.fingerprint,
            )
            await self.repository.add(item)
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.reasoning_for_decision(decision.id)
            if existing is not None:
                return existing, False
            raise PolicyError("Decision reasoning could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def get(self, mission_id: str) -> MissionDecisionReasoning:
        item = await self.repository.reasoning_for_mission(mission_id)
        if item is None:
            raise NotFoundError("Mission decision reasoning not found")
        return item
