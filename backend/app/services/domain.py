from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.ai.fake import FakeEmbeddingModel
from app.core.domain import (
    Actor,
    ConversationStatus,
    InceptionStatus,
    InvalidOrigin,
    MissionStatus,
    require_creator,
    transition,
)
from app.models.entities import Agent, ConsciousMemory, Conversation, Inception, Message, Mission, MissionPlan, Universe
from app.repositories.domain import MEMORY_LAYERS, DomainRepository


class NotFoundError(Exception):
    pass


class LivingCoreService:
    def __init__(self, repository: DomainRepository) -> None:
        self.repo = repository
        self.embeddings = FakeEmbeddingModel()

    async def _owned(self, model, entity_id: str, actor: Actor, lock: bool = False):
        entity = await (self.repo.get_for_update(model, entity_id) if lock else self.repo.get(model, entity_id))
        if entity is None:
            raise NotFoundError(f"{model.__name__} not found")
        owner = await self.repo.owner_id(model, entity_id)
        if owner != actor.id:
            raise NotFoundError(f"{model.__name__} not found")
        return entity

    async def conversations(self, actor: Actor):
        require_creator(actor, "control GOD")
        return await self.repo.list_for_creator(Conversation, actor.id)

    async def create_conversation(self, actor: Actor, title: str, correlation_id: str):
        require_creator(actor, "control GOD")
        item = await self.repo.add(Conversation(creator_id=actor.id, title=title, status=ConversationStatus.ACTIVE.value))
        await self.repo.add_event("conversation_created", "conversation", item.id, actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item

    async def conversation(self, actor: Actor, entity_id: str):
        require_creator(actor, "control GOD")
        return await self._owned(Conversation, entity_id, actor)

    async def add_message(self, actor: Actor, entity_id: str, content: str, metadata: dict[str, Any], correlation_id: str):
        require_creator(actor, "speak directly with GOD")
        conversation = await self._owned(Conversation, entity_id, actor, lock=True)
        if conversation.status != ConversationStatus.ACTIVE.value:
            transition("conversation", ConversationStatus(conversation.status), ConversationStatus.ACTIVE)
        message = await self.repo.add(Message(
            conversation_id=entity_id, actor_id=actor.id, role=actor.role, content=content,
            route="god", metadata_json=metadata, correlation_id=correlation_id,
        ))
        await self.repo.add_event("conversation_message_added", "conversation", entity_id, actor.id, actor.role,
                                  correlation_id, {"message_id": message.id})
        await self.repo.commit()
        return message

    async def close_conversation(self, actor: Actor, entity_id: str, correlation_id: str):
        item = await self._owned(Conversation, entity_id, actor, lock=True)
        item.status = transition("conversation", ConversationStatus(item.status), ConversationStatus.CLOSED)
        await self.repo.add_event("conversation_closed", "conversation", item.id, actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item

    async def archive_conversation(self, actor: Actor, entity_id: str, correlation_id: str):
        item = await self._owned(Conversation, entity_id, actor, lock=True)
        item.status = transition("conversation", ConversationStatus(item.status), ConversationStatus.ARCHIVED)
        await self.repo.add_event("conversation_archived", "conversation", item.id, actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item

    async def inceptions(self, actor: Actor):
        require_creator(actor, "view Inceptions")
        return await self.repo.list_for_creator(Inception, actor.id)

    async def inception(self, actor: Actor, entity_id: str):
        require_creator(actor, "view Inceptions")
        return await self._owned(Inception, entity_id, actor)

    async def create_inception(self, actor: Actor, conversation_id: str, source_message_id: str,
                               title: str, description: str, correlation_id: str):
        conversation = await self._owned(Conversation, conversation_id, actor, lock=True)
        source = await self.repo.source_message(conversation.id, source_message_id)
        if source is None:
            raise InvalidOrigin("Inception requires a message from its Conversation")
        item = await self.repo.add(Inception(
            conversation_id=conversation.id, source_message_id=source.id, title=title,
            description=description, status=InceptionStatus.PROPOSED.value,
            trinity_assessment_json={},
        ))
        item.conversation = conversation
        await self.repo.add_event("inception_created", "inception", item.id, actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item

    async def transition_inception(self, actor: Actor, entity_id: str, target: InceptionStatus,
                                   correlation_id: str, reason: str | None = None):
        item = await self._owned(Inception, entity_id, actor, lock=True)
        if target in {InceptionStatus.APPROVED, InceptionStatus.REJECTED}:
            require_creator(actor, f"{target.value} Inception")
        next_status = transition("inception", InceptionStatus(item.status), target)
        if target == InceptionStatus.CANCELLED:
            mission = await self.repo.mission_for_inception(item.id, lock=True)
            if mission is not None:
                mission_state = MissionStatus(mission.status)
                if mission_state not in {MissionStatus.DRAFTED, MissionStatus.PLANNED, MissionStatus.VALIDATED}:
                    raise InvalidOrigin(f"Cannot cancel Inception while Mission is {mission.status}")
                mission.status = transition("mission", mission_state, MissionStatus.CANCELLED)
                await self.repo.add_event("mission_cancelled", "mission", mission.id, actor.id, actor.role,
                                          correlation_id, {"reason": "inception_cancelled"})
        item.status = next_status
        if target in {InceptionStatus.APPROVED, InceptionStatus.REJECTED}:
            item.decided_at = datetime.now(timezone.utc)
            item.decided_by = actor.id
            item.decision_reason = reason
        event = {InceptionStatus.AWAITING_CREATOR_DECISION: "inception_submitted",
                 InceptionStatus.APPROVED: "inception_approved", InceptionStatus.REJECTED: "inception_rejected",
                 InceptionStatus.CANCELLED: "inception_cancelled"}[target]
        await self.repo.add_event(event, "inception", item.id, actor.id, actor.role, correlation_id, {"reason": reason})
        await self.repo.commit()
        return item

    async def chronicles(self, actor: Actor, limit: int, offset: int):
        require_creator(actor, "read the Chronicle")
        return await self.repo.list_chronicles(limit, offset)

    async def chronicle_integrity(self, actor: Actor):
        require_creator(actor, "verify the Chronicle")
        return await self.repo.verify_chronicle()

    async def pulse(self, actor: Actor, database: dict[str, Any], redis: dict[str, Any], redis_streams: dict[str, Any]):
        require_creator(actor, "read the Pulse")
        counters = await self.repo.pulse_counters()
        integrity = await self.repo.verify_chronicle()
        degraded = not (database["available"] and redis["available"] and integrity.valid)
        return {
            "status": "degraded" if degraded else "healthy",
            "database": database,
            "redis": redis,
            "redis_streams": redis_streams,
            "chronicles_chain": {"valid": integrity.valid, "first_invalid_event_id": integrity.first_invalid_event_id,
                                 "reason": integrity.reason},
            "timestamp": datetime.now(timezone.utc),
            **counters,
        }

    async def universes(self, actor: Actor):
        require_creator(actor, "view Universes")
        return await self.repo.list_all(Universe)

    async def create_universe(self, actor: Actor, code: str, name: str, correlation_id: str):
        require_creator(actor, "create Universes")
        if await self.repo.get_by_code(Universe, code) is not None:
            raise InvalidOrigin(f"Universe {code} already exists")
        item = await self.repo.add(Universe(code=code, name=name, active=False))
        await self.repo.add_event("universe_created", "universe", item.id, actor.id, actor.role, correlation_id,
                                  {"code": code})
        await self.repo.commit()
        return item

    async def set_universe_active(self, actor: Actor, entity_id: str, active: bool, correlation_id: str):
        require_creator(actor, "activate Universes")
        item = await self.repo.get_for_update(Universe, entity_id)
        if item is None:
            raise NotFoundError("Universe not found")
        item.active = active
        await self.repo.add_event("universe_activated" if active else "universe_deactivated", "universe", item.id,
                                  actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item

    async def agents(self, actor: Actor, universe_id: str | None = None):
        require_creator(actor, "view Agents")
        return await self.repo.list_agents(universe_id)

    async def create_agent(self, actor: Actor, code: str, name: str, universe_id: str,
                           capabilities: dict[str, Any], correlation_id: str):
        require_creator(actor, "create Agents")
        universe = await self.repo.get(Universe, universe_id)
        if universe is None:
            raise NotFoundError("Universe not found")
        if await self.repo.get_by_code(Agent, code) is not None:
            raise InvalidOrigin(f"Agent {code} already exists")
        item = await self.repo.add(Agent(code=code, name=name, universe_id=universe.id, active=True,
                                         capabilities_json=capabilities))
        await self.repo.add_event("agent_created", "agent", item.id, actor.id, actor.role, correlation_id,
                                  {"code": code, "universe_id": universe.id})
        await self.repo.commit()
        return item

    async def set_agent_active(self, actor: Actor, entity_id: str, active: bool, correlation_id: str):
        require_creator(actor, "activate Agents")
        item = await self.repo.get_for_update(Agent, entity_id)
        if item is None:
            raise NotFoundError("Agent not found")
        item.active = active
        await self.repo.add_event("agent_activated" if active else "agent_deactivated", "agent", item.id,
                                  actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item

    async def _memory_scope(self, actor: Actor, layer: str, scope_id: str) -> str:
        """Conversation and Mission memory stay behind ownership; Universe memory is global to the Creator."""
        if layer not in MEMORY_LAYERS:
            raise NotFoundError("Unknown memory layer")
        if layer == "conversation":
            return (await self._owned(Conversation, scope_id, actor)).id
        if layer == "mission":
            return (await self._owned(Mission, scope_id, actor)).id
        universe = await self.repo.get(Universe, scope_id)
        if universe is None:
            raise NotFoundError("Universe not found")
        return universe.id

    async def memory(self, actor: Actor, layer: str, scope_id: str):
        require_creator(actor, "read memory")
        return await self.repo.list_memory(layer, await self._memory_scope(actor, layer, scope_id))

    async def remember(self, actor: Actor, layer: str, scope_id: str, key: str, value: dict[str, Any],
                       correlation_id: str):
        require_creator(actor, "write memory")
        scope = await self._memory_scope(actor, layer, scope_id)
        entry = await self.repo.upsert_memory(layer, scope, key, value)
        await self.repo.add_event(f"{layer}_memory_written", f"{layer}_memory", entry.id, actor.id, actor.role,
                                  correlation_id, {"scope_id": scope, "key": key})
        await self.repo.commit()
        return entry

    async def conscious_memories(self, actor: Actor, source_type: str | None, limit: int, offset: int):
        require_creator(actor, "read conscious memory")
        return await self.repo.list_conscious_memory(source_type, limit, offset)

    async def record_conscious_memory(self, actor: Actor, source_type: str, source_id: str, content: str,
                                      metadata: dict[str, Any], correlation_id: str):
        require_creator(actor, "write conscious memory")
        item = await self.repo.add(ConsciousMemory(source_type=source_type, source_id=source_id, content=content,
                                                   metadata_json=metadata,
                                                   embedding=await self.embeddings.embed(content)))
        await self.repo.add_event("conscious_memory_recorded", "conscious_memory", item.id, actor.id, actor.role,
                                  correlation_id, {"source_type": source_type, "source_id": source_id})
        await self.repo.commit()
        return item

    async def missions(self, actor: Actor):
        require_creator(actor, "view Missions")
        return await self.repo.list_for_creator(Mission, actor.id)

    async def mission(self, actor: Actor, entity_id: str):
        require_creator(actor, "view Missions")
        return await self._owned(Mission, entity_id, actor)

    async def create_mission(self, actor: Actor, inception_id: str, title: str, objective: str, correlation_id: str):
        inception = await self._owned(Inception, inception_id, actor, lock=True)
        if inception.status != InceptionStatus.APPROVED.value:
            raise InvalidOrigin("Mission requires an approved Inception")
        item = await self.repo.add(Mission(
            inception_id=inception.id, creator_id=actor.id, title=title, objective=objective,
            status=MissionStatus.DRAFTED.value, authorization_json={},
        ))
        await self.repo.add_event("mission_created", "mission", item.id, actor.id, actor.role, correlation_id,
                                  {"inception_id": inception.id})
        await self.repo.commit()
        return item

    async def transition_mission(self, actor: Actor, entity_id: str, target: MissionStatus,
                                 correlation_id: str, plan: dict[str, Any] | None = None):
        item = await self._owned(Mission, entity_id, actor, lock=True)
        if target == MissionStatus.AUTHORIZED:
            require_creator(actor, "authorize Mission")
        item.status = transition("mission", MissionStatus(item.status), target)
        if target == MissionStatus.PLANNED:
            await self.repo.add(MissionPlan(mission_id=item.id, strategy=(plan or {}).get("strategy", ""),
                                            completion_criteria_json=(plan or {}).get("completion_criteria", {})))
        if target == MissionStatus.AUTHORIZED:
            item.authorization_json = {"authorized_by": actor.id, "authorized_at": datetime.now(timezone.utc).isoformat(),
                                       "correlation_id": correlation_id}
        event = {MissionStatus.PLANNED: "mission_planned", MissionStatus.VALIDATED: "mission_validated",
                 MissionStatus.AUTHORIZED: "mission_authorized", MissionStatus.CANCELLED: "mission_cancelled"}[target]
        await self.repo.add_event(event, "mission", item.id, actor.id, actor.role, correlation_id)
        await self.repo.commit()
        return item
