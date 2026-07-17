from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.core.domain import Actor, DomainError, require_creator
from app.core.rockmam import build_assessment
from app.core.sophia import build_understanding
from app.models.rockmam import RockmamPossibilityAssessment
from app.models.sophia import SophiaUnderstanding
from app.repositories.trinity import TrinityRepository
from app.services.domain import NotFoundError


class TrinityError(DomainError):
    pass


@dataclass(frozen=True)
class TrinityResult:
    understanding: SophiaUnderstanding
    assessment: RockmamPossibilityAssessment
    understanding_created: bool
    assessment_created: bool


class TrinityOrchestrationService:
    def __init__(self, repository: TrinityRepository) -> None:
        self.repository = repository

    async def orchestrate(
        self,
        actor: Actor,
        god_interaction_id: str,
        correlation_id: str,
    ) -> TrinityResult:
        require_creator(actor, "orchestrate the Trinity")
        interaction = await self.repository.god_interaction(god_interaction_id, lock=True)
        if interaction is None:
            await self.repository.rollback()
            raise NotFoundError("GOD interaction not found")
        if interaction.interaction_type != "POTENTIAL":
            await self.repository.rollback()
            raise TrinityError("Trinity orchestration requires a POTENTIAL GOD interaction")

        try:
            understanding = await self.repository.understanding(interaction.id)
            understanding_created = False
            if understanding is None:
                document = build_understanding(interaction)
                understanding = await self.repository.add_understanding(
                    SophiaUnderstanding(
                        god_interaction_id=interaction.id,
                        conversation_id=interaction.conversation_id,
                        understanding_type=document.understanding_type.value,
                        understanding_payload=document.payload,
                        source_fingerprint=document.source_fingerprint,
                        understanding_fingerprint=document.fingerprint,
                    )
                )
                understanding_created = True
                await self.repository.add_event(
                    "sophia_understanding_created",
                    "god_conversation_interaction",
                    interaction.id,
                    actor.id,
                    actor.role,
                    correlation_id,
                    {
                        "understanding_id": understanding.id,
                        "god_interaction_id": interaction.id,
                        "conversation_id": interaction.conversation_id,
                        "understanding_type": understanding.understanding_type,
                        "source_fingerprint": understanding.source_fingerprint,
                        "understanding_fingerprint": understanding.understanding_fingerprint,
                    },
                )

            assessment = await self.repository.assessment(understanding.id)
            assessment_created = False
            if assessment is None:
                assessment_document = build_assessment(understanding)
                assessment = await self.repository.add_assessment(
                    RockmamPossibilityAssessment(
                        sophia_understanding_id=understanding.id,
                        conversation_id=understanding.conversation_id,
                        assessment_result=assessment_document.result.value,
                        assessment_payload=assessment_document.payload,
                        source_fingerprint=assessment_document.source_fingerprint,
                        assessment_fingerprint=assessment_document.fingerprint,
                    )
                )
                assessment_created = True
                await self.repository.add_event(
                    "rockmam_possibility_assessment_created",
                    "sophia_understanding",
                    understanding.id,
                    actor.id,
                    actor.role,
                    correlation_id,
                    {
                        "assessment_id": assessment.id,
                        "sophia_understanding_id": understanding.id,
                        "conversation_id": understanding.conversation_id,
                        "assessment_result": assessment.assessment_result,
                        "source_fingerprint": assessment.source_fingerprint,
                        "assessment_fingerprint": assessment.assessment_fingerprint,
                    },
                )

            await self.repository.commit()
            return TrinityResult(understanding, assessment, understanding_created, assessment_created)
        except IntegrityError as exc:
            await self.repository.rollback()
            understanding = await self.repository.understanding(interaction.id)
            assessment = await self.repository.assessment(understanding.id) if understanding is not None else None
            if understanding is not None and assessment is not None:
                return TrinityResult(understanding, assessment, False, False)
            raise TrinityError("Trinity orchestration could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise
