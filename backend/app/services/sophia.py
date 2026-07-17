from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.domain import Actor, DomainError, require_creator
from app.core.sophia import build_understanding
from app.models.sophia import SophiaUnderstanding
from app.repositories.sophia import SophiaRepository
from app.services.domain import NotFoundError


class SophiaError(DomainError):
    pass


class SophiaService:
    def __init__(self, repository: SophiaRepository) -> None:
        self.repository = repository

    async def understand(
        self,
        actor: Actor,
        god_interaction_id: str,
        correlation_id: str,
    ) -> tuple[SophiaUnderstanding, bool]:
        require_creator(actor, "request SOPHIA understanding")
        interaction = await self.repository.god_interaction(god_interaction_id, lock=True)
        if interaction is None:
            await self.repository.rollback()
            raise NotFoundError("GOD interaction not found")

        existing = await self.repository.understanding(god_interaction_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        try:
            document = build_understanding(interaction)
            item = await self.repository.add(
                SophiaUnderstanding(
                    god_interaction_id=interaction.id,
                    conversation_id=interaction.conversation_id,
                    understanding_type=document.understanding_type.value,
                    understanding_payload=document.payload,
                    source_fingerprint=document.source_fingerprint,
                    understanding_fingerprint=document.fingerprint,
                )
            )
            await self.repository.add_event(
                interaction.id,
                actor.id,
                actor.role,
                correlation_id,
                {
                    "understanding_id": item.id,
                    "god_interaction_id": interaction.id,
                    "conversation_id": interaction.conversation_id,
                    "understanding_type": item.understanding_type,
                    "source_fingerprint": item.source_fingerprint,
                    "understanding_fingerprint": item.understanding_fingerprint,
                },
            )
            await self.repository.commit()
            return item, True
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.understanding(god_interaction_id)
            if existing is not None:
                return existing, False
            raise SophiaError("SOPHIA understanding could not be persisted atomically") from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def get(self, actor: Actor, god_interaction_id: str) -> SophiaUnderstanding:
        require_creator(actor, "view SOPHIA understanding")
        item = await self.repository.understanding(god_interaction_id)
        if item is None:
            raise NotFoundError("SOPHIA understanding not found")
        return item
