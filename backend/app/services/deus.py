from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable
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
from app.models.entities import Agent, Conversation, Inception, Message, Mission, Universe
from app.repositories.domain import DomainRepository
from app.services.conversation_context import conversation_messages
from app.services.domain import NotFoundError, add_mission_plan

LIVE_ITEMS = 8

# Conversational and bounded contextual commands should stay single-pass. Governance-sensitive
# or substantial execution requests still go through SOPHIA/ROCKMAM. Mission precedence wins.
_MISSION_REQUEST = re.compile(
    r"\b(cri(?:e|ar)|fa(?:ça|ca|zer)|implement(?:e|ar)|execut(?:e|ar)|"
    r"inici(?:e|ar)|constru(?:a|ir)|public(?:e|ar)|deploy|instal(?:e|ar)|remov(?:a|er)|"
    r"alter(?:e|ar)|atualiz(?:e|ar)|configur(?:e|ar)|integr(?:e|ar)|automatiz(?:e|ar)|"
    r"melhor(?:e|ar)|otimiz(?:e|ar)|adicion(?:e|ar)|modific(?:e|ar)|repar(?:e|ar)|"
    r"reescrev(?:a|er)|cancel(?:e|ar)|autoriz(?:e|ar)|aprov(?:e|ar))\b",
    re.IGNORECASE,
)
_SIMPLE_ACTIONS = frozenset({
    "continue",
    "prossiga",
    "mostre",
    "verifique",
    "repita",
    "abra",
    "feche",
    "corrija isso",
    "corrija isto",
    "corrija esse erro",
    "corrija o erro",
})

_BOUNDED_FOLLOWUP = re.compile(
    r"^\s*(continue|prossiga|mostre|verifique|repita|explique|responda|resuma|"
    r"melhore|otimize|corrija|reescreva|simplifique)\b",
    re.IGNORECASE,
)
_HIGH_IMPACT_TARGET = re.compile(
    r"\b(produ[cç][aã]o|deploy|publica[cç][aã]o|publique|publicar|seguran[cç]a|governan[cç]a|"
    r"pagamentos?|dinheiro|credenciais?|senhas?|chaves?|permiss[oõ]es|banco\s+de\s+dados|"
    r"migra[cç][aã]o|infraestrutura|backend|frontend|c[oó]digo|api)\b",
    re.IGNORECASE,
)


def _is_simple_action(content: str) -> bool:
    # Exact normalized lookup is cheaper and cannot exhibit regex backtracking on user input.
    return content.casefold().rstrip(".!?").rstrip() in _SIMPLE_ACTIONS


def _is_bounded_followup(content: str) -> bool:
    normalized = " ".join(content.split())
    if not _BOUNDED_FOLLOWUP.search(normalized):
        return False
    if _HIGH_IMPACT_TARGET.search(normalized):
        return False
    # Short contextual turns such as "continue o projeto", "melhore isso" and
    # "corrija esse erro" should not pay for SOPHIA + ROCKMAM before DEUS can answer.
    return len(normalized.split()) <= 14
_DIALOGUE_OPENING = re.compile(
    r"^\s*(oi|olá|ola|bom dia|boa tarde|boa noite|deus\b|status\b|"
    r"o que\b|qual\b|quais\b|como\b|quando\b|onde\b|quem\b|"
    r"por que\b|porque\b|quanto\b|quantos\b|me diga\b|me explique\b|"
    r"explique\b|entendeu\b|e (isso|agora|ele|ela|eles|elas)\b)",
    re.IGNORECASE,
)


def needs_trinity(content: str) -> bool:
    """Route only substantial or governance-sensitive work through the full Trinity."""
    normalized = " ".join(content.split())
    if not normalized:
        return False
    if _is_simple_action(normalized) or _is_bounded_followup(normalized):
        return False
    if _MISSION_REQUEST.search(normalized):
        return True
    if "?" in normalized or _DIALOGUE_OPENING.search(normalized):
        return False
    # Ambiguous non-dialogue statements still fail closed into SOPHIA.
    return True


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


def readiness_of(universes: list[Universe], agents: list[Agent]) -> dict[str, UniverseReadiness]:
    staffed = {agent.universe_id for agent in agents if agent.active}
    return {
        universe.code: (
            UniverseReadiness.INACTIVE if not universe.active
            else UniverseReadiness.READY if universe.id in staffed
            else UniverseReadiness.NO_ACTIVE_AGENT
        )
        for universe in universes
    }


RUNNING_MISSION = {MissionStatus.AUTHORIZED.value, MissionStatus.DISTRIBUTED.value, MissionStatus.EXECUTING.value}
READINESS_TEXT = {
    UniverseReadiness.READY: "ready",
    UniverseReadiness.INACTIVE: "inactive",
    UniverseReadiness.NO_ACTIVE_AGENT: "active but without an active Agent",
    UniverseReadiness.UNKNOWN: "unknown",
}


@dataclass(frozen=True)
class SystemSnapshot:
    readiness: dict[str, UniverseReadiness]
    running: list[Mission]
    awaiting_authorization: list[Mission]


async def system_snapshot(repo: DomainRepository, creator_id: str) -> SystemSnapshot:
    """The live facts DEUS answers from. Queries run one after another: they share one DB session."""
    agents = await repo.list_agents(None)
    universes = await repo.list_all(Universe)
    missions = await repo.list_for_creator(Mission, creator_id)
    return SystemSnapshot(
        readiness=readiness_of(universes, agents),
        running=[mission for mission in missions if mission.status in RUNNING_MISSION],
        awaiting_authorization=[mission for mission in missions if mission.status == MissionStatus.VALIDATED.value],
    )


def _listed(items: list[str]) -> str:
    shown = ", ".join(items[:LIVE_ITEMS])
    return shown + (f" and {len(items) - LIVE_ITEMS} more" if len(items) > LIVE_ITEMS else "")


def live_context_note(snapshot: SystemSnapshot) -> str:
    """One system line of current facts, so status questions get specific answers."""
    # Every Universe is listed: DEUS is told to answer only from these facts.
    universes = (
        ", ".join(f"{code} {READINESS_TEXT[state]}" for code, state in sorted(snapshot.readiness.items()))
        if snapshot.readiness else "none exist yet"
    )
    running = _listed([f'"{m.title}" ({m.status})' for m in snapshot.running]) or "none"
    awaiting = _listed([f'"{m.title}"' for m in snapshot.awaiting_authorization]) or "none"
    return (
        f"Live system state right now. Universes: {universes}. "
        f"Missions under way, each with its exact status (only 'executing' has started work): {running}. "
        f"Missions validated and awaiting the Creator's authorization: {awaiting}."
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
        context_builder=None,
    ) -> None:
        self.repo = repository
        self.router = router
        self.provider = provider
        self.model = model
        self.trinity = trinity
        self.context_builder = context_builder

    async def _reason(
        self, actor: Actor, content: str, history: list[Message], snapshot: Awaitable[SystemSnapshot],
    ) -> TrinityOutcome:
        """Run the Trinity over the Creator's message. It fails open: DEUS still answers.

        ``snapshot`` is already being fetched while SOPHIA perceives, so deliberation does not wait for it.
        """
        if self.trinity is None or not needs_trinity(content):
            return TrinityOutcome()
        stage = "perception"
        intent: IntentEnvelope | None = None
        try:
            recent = [item.content for item in history if item.role == "creator"][:-1]
            intent = await self.trinity.perceive(content, recent, creator_id=actor.id)
            if not self.trinity.calls_for_deliberation(intent):
                return TrinityOutcome(intent=intent)
            stage = "deliberation"
            readiness = (await snapshot).readiness
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

    async def respond(self, actor: Actor, conversation_id: str, content: str, correlation_id: str, commit_guard=None) -> DeusReply:
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
        if self.context_builder is not None:
            # Make the turn visible to the builder's independent, short read transaction.
            await self.repo.commit()
        history = await self.repo.list_messages(conversation_id, limit=20)
        system_notes: list[str] = []
        outcome = TrinityOutcome()
        # The builder already reads live state for text and voice. Only fetch an
        # additional snapshot here when Trinity needs readiness or no builder exists.
        if self.context_builder is None or (self.trinity is not None and needs_trinity(content)):
            # These DB reads overlap SOPHIA's model call; nothing else touches the session meanwhile.
            snapshot_task = asyncio.ensure_future(system_snapshot(self.repo, actor.id))
            outcome = await self._reason(actor, content, history, snapshot_task)
            try:
                system_notes.append(live_context_note(await snapshot_task))
            except Exception as exc:
                logger.bind(component="deus", error_type=exc.__class__.__name__).warning(
                    "live system context unavailable"
                )
        context_packet = None
        if self.context_builder is not None:
            context_packet = await self.context_builder.build(actor.id, conversation_id, content, 'text', history)
            messages = context_packet.messages
        else:
            messages = conversation_messages(history, system_notes=system_notes)
        metadata = {
            "conversation_id": conversation_id,
            "creator_id": actor.id,
            "route": "deus",
            "cache_sensitivity": "PRIVATE",
            "cache_tags": [f"conversation:{conversation_id}", "route:deus"],
            "tool_state_class": "read_only",
            "latency_class": "interactive",
            "skip_health_probe": True,
        }
        if context_packet is not None:
            creator_message.metadata_json = {**creator_message.metadata_json, 'knowledge_project_id':context_packet.trace['project_id']}
            metadata.update({'cache_policy': 'bypass', 'knowledge_version': str(context_packet.trace['knowledge_epoch']), 'retrieval_fingerprint': context_packet.trace['retrieval_fingerprint'], 'context_trace_id': context_packet.trace_id})
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
            metadata_json={"provider": inference.provider, "model": inference.model, **({"context_trace_id": context_packet.trace_id} if context_packet else {})},
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
        from app.config import settings
        if settings.deus_knowledge_ingestion_enabled:
            from app.knowledge.contracts import Candidate, Scope
            from app.knowledge.service import KnowledgeConflict, KnowledgeService
            for entry in [creator_message, deus_message]:
                if entry.role == 'deus' and (not context_packet or len(context_packet.trace['dependency_revision_ids']) > 32):
                    continue
                try:
                    written = await KnowledgeService(self.repo.session).write(
                        Scope(creator_id=actor.id),
                        Candidate(
                            title='Conversa: ' + entry.role,
                            content=entry.content,
                            kind='derived_note' if entry.role == 'deus' else 'document',
                            source_type='message',
                            source_id=entry.id,
                            project_id=context_packet.trace['project_id'] if context_packet else None,
                            dependencies=(
                                context_packet.trace['dependency_revision_ids']
                                if entry.role == 'deus' and context_packet
                                else []
                            ),
                        ),
                        'message:' + entry.id,
                    )
                except KnowledgeConflict as exc:
                    # Knowledge is a secondary projection of a conversation turn. A source
                    # retrieved before inference can legitimately expire while the model is
                    # answering (diagnostic observations are intentionally short-lived).
                    # Preserve the successful Creator/DEUS exchange and fail closed only for
                    # the derived knowledge item instead of turning a good reply into HTTP 500.
                    logger.bind(
                        component='deus_knowledge_ingestion',
                        conversation_id=conversation_id,
                        message_id=entry.id,
                        role=entry.role,
                        conflict=str(exc),
                    ).warning('conversation knowledge projection skipped')
                    continue
                if entry.role == 'creator' and context_packet:
                    from app.services.deus_context import bind_question_source
                    entry.metadata_json = {**entry.metadata_json, 'knowledge_revision_id':written.revision_id}
                    context_packet.trace['dependency_revision_ids'] = await bind_question_source(
                        self.repo.session, actor.id, context_packet.trace_id,
                        context_packet.trace['dependency_revision_ids'], written.revision_id)
        reply = DeusReply(
            creator_message_id=creator_message.id,
            deus_message_id=deus_message.id,
            conversation_id=conversation_id,
            response=inference.content,
            provider=inference.provider,
            model=inference.model,
            inception=inception,
        )
        if commit_guard is not None:
            await commit_guard(reply)
        await self.repo.commit()
        return reply
