from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from app.cognition.contracts import IntentEnvelope
from app.cognition.trinity import RockmamVerdict, TrinityDeliberation, TrinityEngine, UniverseReadiness
from app.core.domain import (
    Actor,
    ConversationStatus,
    InceptionStatus,
    InvalidOrigin,
    MissionStatus,
    require_creator,
    transition,
)
from app.inference.contracts import InferenceRequest, ModelRequirements
from app.inference.router import ModelRouter
from app.models.entities import Conversation, Inception, Message, Mission, Universe
from app.repositories.domain import DomainRepository
from app.services.domain import NotFoundError, add_mission_plan

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


BLOCKER_TEXT = {
    UniverseReadiness.INACTIVE: "is not active",
    UniverseReadiness.NO_ACTIVE_AGENT: "has no active Agent",
    UniverseReadiness.UNKNOWN: "does not exist yet",
}


def proposal_note(deliberation: TrinityDeliberation) -> str:
    """What DEUS is told about the Trinity's work, so it can present it without claiming execution."""
    summary = (
        "SOPHIA and ROCKMAM have just deliberated on the Creator's latest message. "
        f"Mission \"{deliberation.title}\": {deliberation.rockmam.objective} "
        f"The plan has {len(deliberation.mission_plan.steps)} steps. "
    )
    if deliberation.verdict.result == RockmamVerdict.VIABLE:
        return summary + (
            "ROCKMAM judged it viable and has prepared the Mission: planned and validated, ready to start. "
            "It has NOT started. It waits only for the Creator's authorization. Briefly present it and "
            "tell the Creator to say \"autoriza\" to start it or \"cancela\" to drop it."
        )
    blockers = "; ".join(
        f"Universe {blocker.universe} {BLOCKER_TEXT[blocker.reason]}" for blocker in deliberation.verdict.blockers
    )
    return summary + (
        f"ROCKMAM found it is not viable yet: {blockers}. Nothing was prepared or executed. Briefly "
        "explain what the Creator must set up first."
    )


async def universe_readiness(repo: DomainRepository) -> dict[str, UniverseReadiness]:
    """Which Universes could take a Mission step right now."""
    staffed = {agent.universe_id for agent in await repo.list_agents(None) if agent.active}
    return {
        universe.code: (
            UniverseReadiness.INACTIVE if not universe.active
            else UniverseReadiness.READY if universe.id in staffed
            else UniverseReadiness.NO_ACTIVE_AGENT
        )
        for universe in await repo.list_all(Universe)
    }


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
            readiness = await universe_readiness(self.repo)
            deliberation = await self.trinity.deliberate(content, intent, readiness, creator_id=actor.id)
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
        summary = {
            "id": inception.id,
            "title": inception.title,
            "status": inception.status,
            "verdict": deliberation.verdict.result.value,
        }
        if deliberation.verdict.result != RockmamVerdict.VIABLE:
            return summary
        mission = await self._prepare_mission(actor, inception, deliberation, correlation_id)
        return {**summary, "status": inception.status, "mission_id": mission.id, "mission_status": mission.status}

    async def _prepare_mission(
        self,
        actor: Actor,
        inception: Inception,
        deliberation: TrinityDeliberation,
        correlation_id: str,
    ) -> Mission:
        """A viable request is the Creator's own ask, so ROCKMAM carries it to a validated Mission.

        Only authorization — the step that lets work begin — is left for the Creator.
        """
        inception.status = transition(
            "inception", InceptionStatus.AWAITING_CREATOR_DECISION, InceptionStatus.APPROVED,
        )
        inception.decided_at = datetime.now(timezone.utc)
        # ROCKMAM made this call, not the Creator: the Creator's decision is the authorization
        # that lets the work begin, and the record has to say who decided what.
        inception.decided_by = "rockmam"
        inception.decision_reason = "ROCKMAM judged the Mission viable; it waits for the Creator's authorization."
        await self.repo.add_event(
            "inception_approved", "inception", inception.id, actor.id, actor.role, correlation_id,
            {"origin": "trinity", "reason": inception.decision_reason},
        )
        mission = await self.repo.add(Mission(
            inception_id=inception.id, creator_id=actor.id, title=deliberation.title,
            objective=deliberation.rockmam.objective, status=MissionStatus.DRAFTED.value, authorization_json={},
        ))
        await self.repo.add_event(
            "mission_created", "mission", mission.id, actor.id, actor.role, correlation_id,
            {"inception_id": inception.id, "origin": "trinity"},
        )
        await add_mission_plan(self.repo, mission.id, deliberation.mission_plan.model_dump(mode="json"))
        mission.status = transition("mission", MissionStatus.DRAFTED, MissionStatus.PLANNED)
        await self.repo.add_event("mission_planned", "mission", mission.id, actor.id, actor.role, correlation_id,
                                  {"origin": "trinity"})
        mission.status = transition("mission", MissionStatus.PLANNED, MissionStatus.VALIDATED)
        await self.repo.add_event("mission_validated", "mission", mission.id, actor.id, actor.role, correlation_id,
                                  {"origin": "trinity", "verdict": deliberation.verdict.result.value})
        inception.trinity_assessment_json = {**inception.trinity_assessment_json, "mission_id": mission.id}
        return mission

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
