from __future__ import annotations

import asyncio
import uuid

import pytest

from app.cognition.trinity import TrinityEngine, UniverseReadiness
from app.core.domain import Actor
from app.inference.contracts import InferenceRequest, InferenceResponse
from app.models.entities import Agent, Conversation, Message, Mission, Universe
from app.services.conversation_context import SYSTEM_PROMPT
from app.services.deus import (
    DeusConversationService,
    SystemSnapshot,
    live_context_note,
    needs_trinity,
)


class StubRouter:
    def __init__(self) -> None:
        self.requests: list[InferenceRequest] = []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        return InferenceResponse(provider="stub", model="stub-model", content="DEUS response")


class FakeRepository:
    def __init__(self, actor: Actor) -> None:
        self.actor = actor
        self.conversation = Conversation(
            id=str(uuid.uuid4()), creator_id=actor.id, title="Creator", status="active"
        )
        self.messages: list[Message] = []
        self.universes: list[Universe] = []
        self.agents: list[Agent] = []
        self.missions: list[Mission] = []
        self.events: list[dict] = []
        self.commits = 0

    async def get(self, model, entity_id):
        if model is Conversation and entity_id == self.conversation.id:
            return self.conversation
        return None

    async def owner_id(self, model, entity_id):
        if model is Conversation and entity_id == self.conversation.id:
            return self.actor.id
        return None

    async def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = str(uuid.uuid4())
        if isinstance(entity, Message):
            self.messages.append(entity)
        return entity

    async def list_all(self, model):
        return self.universes if model is Universe else []

    async def list_agents(self, universe_id):
        return [agent for agent in self.agents if universe_id is None or agent.universe_id == universe_id]

    async def list_for_creator(self, model, creator_id):
        return [mission for mission in self.missions if mission.creator_id == creator_id] if model is Mission else []

    async def list_messages(self, conversation_id: str, limit: int = 20):
        return [message for message in self.messages if message.conversation_id == conversation_id][-limit:]

    async def add_event(self, event_type, aggregate_type, aggregate_id, actor_id, actor_role, correlation_id, payload=None):
        self.events.append({
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "correlation_id": correlation_id,
            "payload": payload or {},
        })

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
@pytest.mark.parametrize("content, expected_reads", [
    ("Responda brevemente em português ao turno 1", []),
    ("Implemente um novo sistema", ["agents", "universes", "missions"]),
])
async def test_context_backed_turn_fetches_extra_snapshot_only_for_trinity(monkeypatch, content, expected_reads):
    from types import SimpleNamespace

    from app.config import settings

    monkeypatch.setattr(settings, "deus_knowledge_ingestion_enabled", False)
    actor = Actor(str(uuid.uuid4()), "creator")
    reads = []

    class Repository(FakeRepository):
        async def list_agents(self, universe_id):
            reads.append("agents")
            return await super().list_agents(universe_id)

        async def list_all(self, model):
            reads.append("universes")
            return await super().list_all(model)

        async def list_for_creator(self, model, creator_id):
            reads.append("missions")
            return await super().list_for_creator(model, creator_id)

    class ContextBuilder:
        async def build(self, creator_id, conversation_id, content, channel, history):
            return SimpleNamespace(
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": content}],
                trace={"project_id": None, "knowledge_epoch": 1,
                       "retrieval_fingerprint": "test"},
                trace_id="context-trace",
            )

    perceptions = []

    class Trinity:
        async def perceive(self, command, recent, *, creator_id):
            perceptions.append(command)
            return None

        def calls_for_deliberation(self, intent):
            return False

    repo = Repository(actor)
    router = StubRouter()
    service = DeusConversationService(repo, router, provider="stub", model="stub-model",
                                     context_builder=ContextBuilder(), trinity=Trinity())
    reply = await service.respond(actor, repo.conversation.id, content, "turn")

    assert reply.response == "DEUS response"
    assert router.requests[0].messages[-1]["content"] == content
    assert reads == expected_reads
    assert perceptions == ([content] if expected_reads else [])


@pytest.mark.asyncio
async def test_deus_uses_model_router_and_persists_both_sides_of_conversation() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    router = StubRouter()
    service = DeusConversationService(repo, router, provider="stub", model="stub-model")

    result = await service.respond(actor, repo.conversation.id, "What is our status?", str(uuid.uuid4()))

    assert result.response == "DEUS response"
    assert result.provider == "stub"
    assert [message.role for message in repo.messages] == ["creator", "deus"]
    assert repo.messages[0].content == "What is our status?"
    assert repo.messages[1].content == "DEUS response"
    assert router.requests[0].requirements.preferred_provider == "stub"
    assert router.requests[0].model == "stub-model"
    assert any(message["role"] == "system" and "DEUS" in message["content"] for message in router.requests[0].messages)
    assert repo.events[-1]["event_type"] == "deus_response_generated"
    assert repo.commits == 1


@pytest.mark.asyncio
async def test_deus_keeps_its_model_and_leaves_the_chain_to_the_router() -> None:
    """The router built by bootstrap carries the fallback chain, so DEUS pins the primary's model
    and each fallback still serves its own default (see test_inference_fallback)."""
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    router = StubRouter()
    service = DeusConversationService(repo, router, provider="freellmapi", model="auto:default")

    await service.respond(actor, repo.conversation.id, "What is our status?", str(uuid.uuid4()))

    request = router.requests[0]
    assert request.requirements.preferred_provider == "freellmapi"
    assert request.requirements.fallback_providers == []
    assert request.model == "auto:default"


@pytest.mark.asyncio
async def test_deus_rejects_conversation_owned_by_another_creator() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    other = Actor(str(uuid.uuid4()), "creator")
    service = DeusConversationService(repo, StubRouter(), provider="stub", model="stub-model")

    with pytest.raises(Exception, match="Conversation not found"):
        await service.respond(other, repo.conversation.id, "hello", str(uuid.uuid4()))


def test_deus_fast_path_keeps_dialogue_single_pass_but_governs_execution() -> None:
    assert needs_trinity("Qual é o status disso?") is False
    assert needs_trinity("e agora?") is False
    assert needs_trinity("como ficou o que falamos?") is False
    assert needs_trinity("corrija isso agora") is False
    assert needs_trinity("continue o projeto") is False
    assert needs_trinity("melhore isso") is False
    assert needs_trinity("corrija o código") is True
    assert needs_trinity("você consegue implementar isso?") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["continue", "verifique", "corrija esse erro"])
async def test_bounded_contextual_commands_use_only_the_deus_inference(content: str) -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    router = StubRouter()
    engine = TrinityEngine(router, provider="stub", model="stub-model", min_confidence=0.7)
    service = DeusConversationService(repo, router, provider="stub", model="stub-model", trinity=engine)

    result = await service.respond(actor, repo.conversation.id, content, str(uuid.uuid4()))

    assert result.response == "DEUS response"
    assert [request.metadata["route"] for request in router.requests] == ["deus"]


def test_deus_system_prompt_preserves_recent_dialogue_context() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "continuous conversation" in lowered
    assert "never make the creator repeat context" in lowered
    assert "always reply in brazilian portuguese" in lowered
    assert "do not switch" in lowered
    assert "transcription artifacts" in lowered


def test_deus_system_prompt_shapes_short_spoken_prose() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "one to three short sentences" in lowered
    assert "never use lists" in lowered
    assert "sober" in lowered
    assert "live system state" in lowered


def populated_repository(actor: Actor) -> FakeRepository:
    repo = FakeRepository(actor)
    web = Universe(id=str(uuid.uuid4()), code="WEB", name="Web", active=True)
    content = Universe(id=str(uuid.uuid4()), code="CONTENT", name="Content", active=True)
    finance = Universe(id=str(uuid.uuid4()), code="FINANCE", name="Finance", active=False)
    repo.universes = [web, content, finance]
    repo.agents = [Agent(id=str(uuid.uuid4()), code="web-agent", name="Web", universe_id=web.id, active=True)]
    repo.missions = [
        Mission(id=str(uuid.uuid4()), creator_id=actor.id, title="Landing page", objective="x", status="executing"),
        Mission(id=str(uuid.uuid4()), creator_id=actor.id, title="Newsletter", objective="x", status="validated"),
        Mission(id=str(uuid.uuid4()), creator_id=actor.id, title="Old launch", objective="x", status="manifested"),
        Mission(id=str(uuid.uuid4()), creator_id="someone-else", title="Foreign", objective="x", status="executing"),
    ]
    return repo


@pytest.mark.asyncio
async def test_deus_answers_from_the_live_system_state() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = populated_repository(actor)
    router = StubRouter()
    service = DeusConversationService(repo, router, provider="stub", model="stub-model")

    await service.respond(actor, repo.conversation.id, "Como estão os universos?", str(uuid.uuid4()))

    messages = router.requests[0].messages
    assert messages[0]["content"] == SYSTEM_PROMPT
    live = messages[1]
    assert live["role"] == "system" and live["content"].startswith("Live system state")
    assert "CONTENT active but without an active Agent" in live["content"]
    assert "FINANCE inactive" in live["content"]
    assert "WEB ready" in live["content"]
    assert "Missions under way, each with its exact status" in live["content"]
    assert '"Landing page" (executing).' in live["content"]
    assert 'awaiting the Creator\'s authorization: "Newsletter".' in live["content"]
    assert "Old launch" not in live["content"] and "Foreign" not in live["content"]
    assert messages[-1] == {"role": "user", "content": "Como estão os universos?"}


@pytest.mark.asyncio
async def test_deus_still_answers_when_the_live_state_cannot_be_read() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)

    async def broken(*_args):
        raise RuntimeError("database unavailable")

    repo.list_agents = broken  # type: ignore[method-assign]
    router = StubRouter()
    service = DeusConversationService(repo, router, provider="stub", model="stub-model")

    result = await service.respond(actor, repo.conversation.id, "Status?", str(uuid.uuid4()))

    assert result.response == "DEUS response"
    assert [m["content"] for m in router.requests[0].messages if m["role"] == "system"] == [SYSTEM_PROMPT]


class PerceptionAwaitingSnapshotRouter:
    """Perception only answers once the live snapshot has started, proving the two overlap."""

    def __init__(self, snapshot_started: asyncio.Event) -> None:
        self.snapshot_started = snapshot_started
        self.requests: list[InferenceRequest] = []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        if request.metadata["route"] == "deus":
            return InferenceResponse(provider="stub", model="stub-model", content="Pronto.")
        await asyncio.wait_for(self.snapshot_started.wait(), timeout=1)
        return InferenceResponse(provider="stub", model="stub-model", content=(
            '{"intent_class": "conversation", "summary": "chat", "confidence": 0.99}'
        ))


@pytest.mark.asyncio
async def test_live_snapshot_is_read_while_sophia_perceives() -> None:
    actor = Actor(str(uuid.uuid4()), "creator")
    repo = populated_repository(actor)
    snapshot_started = asyncio.Event()
    list_agents = repo.list_agents

    async def observed_list_agents(universe_id):
        snapshot_started.set()
        return await list_agents(universe_id)

    repo.list_agents = observed_list_agents  # type: ignore[method-assign]
    router = PerceptionAwaitingSnapshotRouter(snapshot_started)
    engine = TrinityEngine(router, provider="stub", model="stub-model", min_confidence=0.7)
    service = DeusConversationService(repo, router, provider="stub", model="stub-model", trinity=engine)

    result = await service.respond(actor, repo.conversation.id, "Hoje o dia está tranquilo", str(uuid.uuid4()))

    assert result.response == "Pronto."
    assert [request.metadata["route"] for request in router.requests] == ["trinity:sophia", "deus"]
    assert not any(event["event_type"] == "trinity_failed" for event in repo.events)


def test_live_context_lists_every_universe() -> None:
    readiness = {f"U{index:02d}": UniverseReadiness.READY for index in range(12)}
    note = live_context_note(SystemSnapshot(readiness=readiness, running=[], awaiting_authorization=[]))
    assert all(f"U{index:02d} ready" in note for index in range(12))

@pytest.mark.asyncio
async def test_deus_reply_survives_stale_knowledge_projection(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.config import settings
    from app.knowledge.service import KnowledgeConflict, KnowledgeService

    actor = Actor(str(uuid.uuid4()), "creator")
    repo = FakeRepository(actor)
    repo.session = object()  # type: ignore[attr-defined]
    router = StubRouter()

    class ContextBuilder:
        async def build(self, creator_id, conversation_id, content, channel, history):
            return SimpleNamespace(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                trace={
                    "project_id": None,
                    "knowledge_epoch": 1,
                    "retrieval_fingerprint": "test",
                    "dependency_revision_ids": ["expired-diagnostic-revision"],
                },
                trace_id="trace-expiring-dependency",
            )

    calls: list[str] = []

    async def stale_projection(self, scope, candidate, key, *args, **kwargs):
        calls.append(candidate.source_id or "")
        raise KnowledgeConflict("dependency unavailable")

    monkeypatch.setattr(settings, "deus_knowledge_ingestion_enabled", True)
    monkeypatch.setattr(KnowledgeService, "write", stale_projection)
    service = DeusConversationService(
        repo,
        router,
        provider="stub",
        model="stub-model",
        context_builder=ContextBuilder(),
    )

    result = await service.respond(
        actor,
        repo.conversation.id,
        "Continue a conversa.",
        str(uuid.uuid4()),
    )

    assert result.response == "DEUS response"
    assert [message.role for message in repo.messages] == ["creator", "deus"]
    assert len(calls) == 2
    # Context-backed turns commit the Creator message before the independent
    # retrieval transaction, then commit the completed reply at the end.
    assert repo.commits == 2
