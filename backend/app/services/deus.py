from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.cognition.contracts import IntentEnvelope
from app.cognition.trinity import RockmamVerdict, TrinityDeliberation, TrinityEngine
from app.core.domain import Actor, ConversationStatus, InceptionStatus, InvalidOrigin, require_creator, transition
from app.inference.contracts import InferenceRequest, ModelRequirements
from app.inference.router import ModelRouter
from app.models.entities import Conversation, Inception, Message, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import NotFoundError

SYSTEM_PROMPT = (
    "You are DEUS, the Creator-facing interface of THE CREATION OS. "
    "Answer the Creator clearly and concisely. Do not claim that an action, Mission, Agent, "
    "Capability, deployment, or external operation occurred unless that fact is present in the "
    "conversation or supplied system context. When execution is required, describe the required "
    "next action rather than pretending it already happened. "
    "Your replies are also spoken aloud to the Creator, so write natural prose: no Markdown, "
    "tables, or code blocks unless the Creator asks for them."
)


@dataclass(frozen=True)
class DeusReply:
    creator_message_id: str
    deus_message_id: str
    conversation_id: str
    response: str
    provider: str
    model: str
    inception: dict[str, str] | None = None


@dataclass(frozen=True)
class TrinityOutcome:
    intent: IntentEnvelope | None = None
    deliberation: TrinityDeliberation | None = None
    failed_stage: str | None = None
    error: str | None = None


def proposal_note(deliberation: TrinityDeliberation) -> str:
    """What DEUS is told about a proposal, so it can present it without claiming it was executed."""
    if deliberation.verdict.result == RockmamVerdict.VIABLE:
        viability = "ROCKMAM judged it viable with the active Universes."
    else:
        needed = ", ".join(deliberation.verdict.unavailable_universes)
        viability = f"ROCKMAM found it needs Universes that are not active yet: {needed}."
    return (
        "SOPHIA and ROCKMAM have just deliberated on the Creator's latest message and proposed an "
        f"Inception titled \"{deliberation.title}\" with the objective: {deliberation.rockmam.objective} "
        f"The plan has {len(deliberation.mission_plan.steps)} steps. {viability} "
        "It now awaits the Creator's decision and nothing has been executed. Briefly present the "
        "proposal and ask the Creator whether to approve it."
    )


class DeusConversationService:
    def __init__(
        self,
        repository: DomainRepository,
        router: ModelRouter,
        *,
        provider: str,
        model: str,
        trinity: TrinityEngine | None = None,
    ) -> None:
        self.repo = repository
        self.router = router
        self.provider = provider
        self.model = model
        self.trinity = trinity

    async def _reason(self, actor: Actor, content: str, history: list[Message]) -> TrinityOutcome:
        """Run the Trinity over the Creator's message. It fails open: DEUS still answers."""
        if self.trinity is None:
            return TrinityOutcome()
        stage = "perception"
        intent: IntentEnvelope | None = None
        try:
            recent = [item.content for item in history if item.role == "creator"][:-1]
            intent = await self.trinity.perceive(content, recent, creator_id=actor.id)
            if not self.trinity.calls_for_deliberation(intent):
                return TrinityOutcome(intent=intent)
            stage = "deliberation"
            universes = {item.code for item in await self.repo.list_all(Universe) if item.active}
            deliberation = await self.trinity.deliberate(content, intent, universes, creator_id=actor.id)
            return TrinityOutcome(intent=intent, deliberation=deliberation)
        except Exception as exc:
            logger.bind(component="trinity", stage=stage, error_type=exc.__class__.__name__).warning(
                "trinity reasoning failed open"
            )
            return TrinityOutcome(intent=intent, failed_stage=stage, error=exc.__class__.__name__)

    async def _record_reasoning(
        self,
        actor: Actor,
        conversation_id: str,
        creator_message: Message,
        outcome: TrinityOutcome,
        correlation_id: str,
    ) -> dict[str, str] | None:
        if outcome.intent is not None:
            await self.repo.add_event(
                "sophia_intent_perceived", "conversation", conversation_id, actor.id, actor.role, correlation_id,
                {
                    "message_id": creator_message.id,
                    "intent_class": outcome.intent.intent_class.value,
                    "confidence": outcome.intent.confidence,
                },
            )
        if outcome.failed_stage is not None:
            await self.repo.add_event(
                "trinity_failed", "conversation", conversation_id, actor.id, actor.role, correlation_id,
                {"message_id": creator_message.id, "stage": outcome.failed_stage, "error": outcome.error},
            )
        deliberation = outcome.deliberation
        if deliberation is None or self.trinity is None:
            return None
        inception = await self.repo.add(Inception(
            conversation_id=conversation_id,
            source_message_id=creator_message.id,
            title=deliberation.title,
            description=deliberation.rockmam.objective,
            status=InceptionStatus.PROPOSED.value,
            trinity_assessment_json=deliberation.assessment_document(
                provider=self.trinity.provider, model=self.trinity.model,
            ),
        ))
        await self.repo.add_event(
            "inception_created", "inception", inception.id, actor.id, actor.role, correlation_id,
            {"origin": "trinity", "message_id": creator_message.id},
        )
        inception.status = transition(
            "inception", InceptionStatus.PROPOSED, InceptionStatus.AWAITING_CREATOR_DECISION,
        )
        await self.repo.add_event(
            "inception_submitted", "inception", inception.id, actor.id, actor.role, correlation_id,
            {"origin": "trinity", "verdict": deliberation.verdict.result.value},
        )
        return {
            "id": inception.id,
            "title": inception.title,
            "status": inception.status,
            "verdict": deliberation.verdict.result.value,
        }

    async def respond(self, actor: Actor, conversation_id: str, content: str, correlation_id: str) -> DeusReply:
        require_creator(actor, "speak with DEUS")
        conversation = await self.repo.get(Conversation, conversation_id)
        owner_id = await self.repo.owner_id(Conversation, conversation_id) if conversation is not None else None
        if conversation is None or owner_id != actor.id:
            raise NotFoundError("Conversation not found")
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise InvalidOrigin("DEUS requires an active Conversation")

        creator_message = await self.repo.add(Message(
            conversation_id=conversation_id,
            actor_id=actor.id,
            role="creator",
            content=content,
            route="deus",
            metadata_json={},
            correlation_id=correlation_id,
        ))
        history = await self.repo.list_messages(conversation_id, limit=20)
        outcome = await self._reason(actor, content, history)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({
            "role": "assistant" if item.role == "deus" else "user",
            "content": item.content,
        } for item in history)
        metadata = {
            "conversation_id": conversation_id,
            "creator_id": actor.id,
            "route": "deus",
            "cache_sensitivity": "PRIVATE",
            "cache_tags": [f"conversation:{conversation_id}", "route:deus"],
            "tool_state_class": "read_only",
        }
        if outcome.deliberation is not None:
            messages.append({"role": "system", "content": proposal_note(outcome.deliberation)})
            # The reply presents this one proposal; a cached reply would present a stale one.
            metadata["cache_policy"] = "bypass"

        inference = await self.router.generate(InferenceRequest(
            messages=messages,
            model=self.model,
            requirements=ModelRequirements(preferred_provider=self.provider),
            metadata=metadata,
        ))
        deus_message = await self.repo.add(Message(
            conversation_id=conversation_id,
            actor_id="deus",
            role="deus",
            content=inference.content,
            route="deus",
            metadata_json={"provider": inference.provider, "model": inference.model},
            correlation_id=correlation_id,
        ))
        # Chronicle writes take a global lock, so they all happen after the model calls.
        inception = await self._record_reasoning(actor, conversation_id, creator_message, outcome, correlation_id)
        await self.repo.add_event(
            "deus_response_generated",
            "conversation",
            conversation_id,
            actor.id,
            actor.role,
            correlation_id,
            {
                "creator_message_id": creator_message.id,
                "deus_message_id": deus_message.id,
                "provider": inference.provider,
                "model": inference.model,
            },
        )
        await self.repo.commit()
        return DeusReply(
            creator_message_id=creator_message.id,
            deus_message_id=deus_message.id,
            conversation_id=conversation_id,
            response=inference.content,
            provider=inference.provider,
            model=inference.model,
            inception=inception,
        )
