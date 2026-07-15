from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.domain import Actor, DomainError, require_creator
from app.core.rockmam import build_assessment
from app.models.rockmam import RockmamPossibilityAssessment
from app.repositories.rockmam import RockmamRepository
from app.services.domain import NotFoundError


class RockmamError(DomainError):
    pass


class RockmamService:
    def __init__(self, repository: RockmamRepository) -> None:
        self.repository = repository

    async def assess(
        self,
        actor: Actor,
        sophia_understanding_id: str,
        correlation_id: str,
    ) -> tuple[RockmamPossibilityAssessment, bool]:
        require_creator(actor, "request ROCKMAM possibility assessment")
        understanding = await self.repository.understanding(sophia_understanding_id, lock=True)
        if understanding is None:
            await self.repository.rollback()
            raise NotFoundError("SOPHIA understanding not found")

        existing = await self.repository.assessment(sophia_understanding_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        try:
            document = build_assessment(understanding)
            item = await self.repository.add(
                RockmamPossibilityAssessment(
                    sophia_understanding_id=understanding.id,
                    conversation_id=understanding.conversation_id,
                    assessment_result=document.result.value,
                    assessment_payload=document.payload,
                    source_fingerprint=document.source_fingerprint,
                    assessment_fingerprint=document.fingerprint,
                )
            )
            await self.repository.add_event(
                understanding.id,
                actor.id,
                actor.role,
                correlation_id,
                {
                    "assessment_id": item.id,
                    "sophia_understanding_id": understanding.id,
                    "conversation_id": understanding.conversation_id,
                    "assessment_result": item.assessment_result,
                    "source_fingerprint": item.source_fingerprint,
                    "assessment_fingerprint": item.assessment_fingerprint,
                },
            )
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.assessment(sophia_understanding_id)
            if existing is not None:
                return existing, False
            raise RockmamError("ROCKMAM assessment could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def get(self, actor: Actor, sophia_understanding_id: str) -> RockmamPossibilityAssessment:
        require_creator(actor, "view ROCKMAM possibility assessment")
        item = await self.repository.assessment(sophia_understanding_id)
        if item is None:
            raise NotFoundError("ROCKMAM assessment not found")
        return item
