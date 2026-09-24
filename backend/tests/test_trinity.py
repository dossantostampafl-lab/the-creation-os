from __future__ import annotations

import json
import uuid

import pytest

from app.cognition.contracts import IntentClass, IntentEnvelope, MissionPlanCandidate
from app.cognition.trinity import (
    RockmamVerdict,
    TrinityEngine,
    TrinityError,
    UniverseReadiness,
    judge,
    parse_json_document,
)
from app.core.domain import Actor
from app.inference.contracts import InferenceRequest, InferenceResponse
from app.models.entities import Agent, Conversation, Inception, Message, Mission, MissionPlan, MissionStep, Universe
from app.services.deus import DeusConversationService

MISSION_INTENT = {"intent_class": "mission_candidate", "summary": "Build a landing page", "confidence": 0.92}
CHAT_INTENT = {"intent_class": "conversation", "summary": "Greeting", "confidence": 0.99}
SOPHIA_REPLY = {
    "opportunities": ["Reach new visitors"],
    "risks": ["Copy may need review"],
    "recommendation": "Build a simple page first.",
}
ROCKMAM_REPLY = {
    "title": "Landing page",
    "synthesis": {
        "objective": "Publish a landing page for the product.",
        "constraints": ["No paid tools"],
        "completion_criteria": ["Page is reachable"],
    },
    "mission_plan": {
        "strategy": "Write, then build.",
        "steps": [
            {"step_key": "write-copy", "title": "Write copy", "description": "Draft the text.",
             "universe": "CONTENT", "position": 1},
            {"step_key": "build-page", "title": "Build page", "description": "Assemble the page.",
             "universe": "WEB", "position": 2, "depends_on": ["write-copy"]},
        ],
    },
}


class ScriptedRouter:
    """Answers each model call with the next scripted reply, in order."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.requests: list[InferenceRequest] = []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        return InferenceResponse(provider="stub", model="stub-model", content=self.replies.pop(0))

    def routes(self) -> list[str]:
        return [request.metadata["route"] for request in self.requests]


def universe(code: str, *, active: bool = True, staffed: bool = True) -> tuple[Universe, Agent | None]:
    item = Universe(id=str(uuid.uuid4()), code=code, name=code.title(), active=active)
    agent = Agent(id=str(uuid.uuid4()), code=f"{code.lower()}-agent", name="Agent", universe_id=item.id, active=True)
    return item, agent if staffed else None


class FakeRepository:
    def __init__(self, actor: Actor, universes: list[tuple[Universe, Agent | None]] | None = None) -> None:
        self.actor = actor
        self.conversation = Conversation(id=str(uuid.uuid4()), creator_id=actor.id, title="Creator", status="active")
        self.universes = [item for item, _ in universes or []]
        self.agents = [agent for _, agent in universes or [] if agent is not None]
        self.messages: list[Message] = []
        self.inceptions: list[Inception] = []
        self.missions: list[Mission] = []
        self.plans: list[MissionPlan] = []
        self.steps: list[MissionStep] = []
        self.events: list[dict] = []
        self.commits = 0

    async def get(self, model, entity_id):
        return self.conversation if model is Conversation and entity_id == self.conversation.id else None

    async def owner_id(self, model, entity_id):
        return self.actor.id if model is Conversation and entity_id == self.conversation.id else None

    async def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = str(uuid.uuid4())
        if isinstance(entity, Message):
            self.messages.append(entity)
        for kind, bucket in ((Inception, self.inceptions), (Mission, self.missions),
                             (MissionPlan, self.plans), (MissionStep, self.steps)):
            if isinstance(entity, kind):
                bucket.append(entity)
        return entity

    async def list_all(self, model):
        return self.universes if model is Universe else []

    async def list_agents(self, universe_id):
        return [agent for agent in self.agents if universe_id is None or agent.universe_id == universe_id]

    async def list_messages(self, conversation_id: str, limit: int = 20):
        return [message for message in self.messages if message.conversation_id == conversation_id][-limit:]

    async def add_event(self, event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id,
                        payload=None):
        self.events.append({"event_type": event_type, "aggregate_id": aggregate_id, "payload": payload or {}})

    async def commit(self):
        self.commits += 1


def service_for(repo: FakeRepository, router: ScriptedRouter) -> DeusConversationService:
    engine = TrinityEngine(router, provider="stub", model="stub-model", min_confidence=0.7)
    return DeusConversationService(repo, router, provider="stub", model="stub-model", trinity=engine)


def creator() -> Actor:
    return Actor(str(uuid.uuid4()), "creator")


def test_parse_json_document_tolerates_markdown_fences_and_prose() -> None:
    reply = 'Here you go:\n```json\n{"intent_class": "conversation", "summary": "Hi", "confidence": 0.5}\n```'

    intent = parse_json_document(reply, IntentEnvelope)

    assert intent.intent_class == IntentClass.CONVERSATION


@pytest.mark.parametrize("reply", ["no json here", '{"intent_class": "dance", "summary": "x", "confidence": 1}'])
def test_parse_json_document_rejects_invalid_replies(reply: str) -> None:
    with pytest.raises(TrinityError):
        parse_json_document(reply, IntentEnvelope)


def test_rockmam_guard_is_viable_only_when_every_universe_can_take_work() -> None:
    plan = MissionPlanCandidate.model_validate(ROCKMAM_REPLY["mission_plan"])
    ready = UniverseReadiness.READY

    assert judge(plan, {"CONTENT": ready, "WEB": ready}).result == RockmamVerdict.VIABLE
    for readiness, reason in (({"CONTENT": ready, "WEB": UniverseReadiness.INACTIVE}, "inactive"),
                              ({"CONTENT": ready, "WEB": UniverseReadiness.NO_ACTIVE_AGENT}, "no_active_agent"),
                              ({"CONTENT": ready}, "unknown")):
        verdict = judge(plan, readiness)
        assert verdict.result == RockmamVerdict.REQUIRES_CREATOR
        assert verdict.unavailable_universes == ["WEB"]
        assert [(blocker.universe, blocker.reason.value) for blocker in verdict.blockers] == [("WEB", reason)]


def test_low_confidence_mission_intent_does_not_deliberate() -> None:
    engine = TrinityEngine(ScriptedRouter([]), provider="stub", model="m", min_confidence=0.7)
    unsure = IntentEnvelope(intent_class=IntentClass.MISSION_CANDIDATE, summary="maybe", confidence=0.4)

    assert not engine.calls_for_deliberation(unsure)


@pytest.mark.asyncio
async def test_viable_request_becomes_a_validated_mission_awaiting_only_authorization() -> None:
    actor = creator()
    repo = FakeRepository(actor, [universe("CONTENT"), universe("WEB")])
    router = ScriptedRouter([
        json.dumps(MISSION_INTENT), json.dumps(SOPHIA_REPLY), json.dumps(ROCKMAM_REPLY), "Ready when you are.",
    ])

    result = await service_for(repo, router).respond(actor, repo.conversation.id, "Build a landing page",
                                                     str(uuid.uuid4()))

    [inception] = repo.inceptions
    [mission] = repo.missions
    # ROCKMAM decided viability; the Creator's decision is still the authorization to come.
    assert inception.status == "approved" and inception.decided_by == "rockmam"
    assert mission.status == "validated"
    assert mission.inception_id == inception.id and mission.creator_id == actor.id
    assert mission.objective == "Publish a landing page for the product."
    assert mission.authorization_json == {}
    [plan] = repo.plans
    assert plan.mission_id == mission.id and plan.strategy == "Write, then build."
    assert [(step.step_key, step.universe, step.depends_on_json) for step in repo.steps] == [
        ("write-copy", "CONTENT", []), ("build-page", "WEB", ["write-copy"]),
    ]
    assert inception.trinity_assessment_json["mission_id"] == mission.id
    assert inception.trinity_assessment_json["verdict"]["result"] == "VIABLE"
    note = router.requests[-1].messages[-1]["content"]
    assert "has NOT started" in note and "autoriza" in note
    assert result.inception == {"id": inception.id, "title": "Landing page", "status": "approved",
                                "verdict": "VIABLE", "mission_id": mission.id, "mission_status": "validated"}
    assert [event["event_type"] for event in repo.events] == [
        "sophia_intent_perceived", "inception_created", "inception_submitted", "inception_approved",
        "mission_created", "mission_planned", "mission_validated", "deus_response_generated",
    ]
    assert repo.commits == 1


@pytest.mark.asyncio
async def test_unviable_request_stays_an_inception_and_names_what_is_missing() -> None:
    actor = creator()
    repo = FakeRepository(actor, [universe("CONTENT"), universe("WEB", active=False)])
    router = ScriptedRouter([
        json.dumps(MISSION_INTENT), json.dumps(SOPHIA_REPLY), json.dumps(ROCKMAM_REPLY), "I have a proposal.",
    ])

    result = await service_for(repo, router).respond(actor, repo.conversation.id, "Build a landing page",
                                                     str(uuid.uuid4()))

    assert router.routes() == ["trinity:sophia", "trinity:sophia", "trinity:rockmam", "deus"]
    assert all(request.metadata["cache_policy"] == "bypass" for request in router.requests)
    [inception] = repo.inceptions
    assert inception.status == "awaiting_creator_decision"
    assert inception.source_message_id == repo.messages[0].id
    assert inception.title == "Landing page"
    assessment = inception.trinity_assessment_json
    assert assessment["sophia"]["risks"] == ["Copy may need review"]
    assert assessment["sophia"]["intent"]["intent_class"] == "mission_candidate"
    assert assessment["rockmam"]["objective"] == "Publish a landing page for the product."
    assert [step["step_key"] for step in assessment["mission_plan"]["steps"]] == ["write-copy", "build-page"]
    assert assessment["verdict"] == {"result": "REQUIRES_CREATOR",
                                     "blockers": [{"universe": "WEB", "reason": "inactive"}],
                                     "unavailable_universes": ["WEB"]}
    assert repo.missions == []
    deus_prompt = router.requests[-1].messages
    assert deus_prompt[-1]["role"] == "system" and "Landing page" in deus_prompt[-1]["content"]
    assert "Universe WEB is not active" in deus_prompt[-1]["content"]
    assert "Nothing was prepared or executed" in deus_prompt[-1]["content"]
    assert result.inception == {"id": inception.id, "title": "Landing page",
                                "status": "awaiting_creator_decision", "verdict": "REQUIRES_CREATOR"}
    assert [event["event_type"] for event in repo.events] == [
        "sophia_intent_perceived", "inception_created", "inception_submitted", "deus_response_generated",
    ]
    assert repo.commits == 1


@pytest.mark.asyncio
async def test_small_talk_is_perceived_but_not_deliberated() -> None:
    actor = creator()
    repo = FakeRepository(actor)
    router = ScriptedRouter([json.dumps(CHAT_INTENT), "Hello, Creator."])

    result = await service_for(repo, router).respond(actor, repo.conversation.id, "Hi DEUS", str(uuid.uuid4()))

    assert router.routes() == ["trinity:sophia", "deus"]
    assert "cache_policy" not in router.requests[-1].metadata
    assert result.inception is None and repo.inceptions == []
    assert [event["event_type"] for event in repo.events] == ["sophia_intent_perceived", "deus_response_generated"]


@pytest.mark.asyncio
async def test_trinity_failure_never_silences_deus() -> None:
    actor = creator()
    repo = FakeRepository(actor)
    router = ScriptedRouter([json.dumps(MISSION_INTENT), json.dumps(SOPHIA_REPLY), "not a plan", "Answer anyway."])

    result = await service_for(repo, router).respond(actor, repo.conversation.id, "Build it", str(uuid.uuid4()))

    assert result.response == "Answer anyway."
    assert result.inception is None and repo.inceptions == []
    failure = next(event for event in repo.events if event["event_type"] == "trinity_failed")
    assert failure["payload"]["stage"] == "deliberation"
    assert failure["payload"]["error"] == "TrinityError"
    assert repo.events[-1]["event_type"] == "deus_response_generated"


@pytest.mark.asyncio
async def test_perception_sees_earlier_creator_messages_but_not_the_latest_twice() -> None:
    actor = creator()
    repo = FakeRepository(actor)
    router = ScriptedRouter([json.dumps(CHAT_INTENT), "One.", json.dumps(CHAT_INTENT), "Two."])
    service = service_for(repo, router)

    await service.respond(actor, repo.conversation.id, "first message", str(uuid.uuid4()))
    await service.respond(actor, repo.conversation.id, "second message", str(uuid.uuid4()))

    perception = router.requests[2].messages[-1]["content"]
    assert "- first message" in perception
    assert perception.count("second message") == 1
