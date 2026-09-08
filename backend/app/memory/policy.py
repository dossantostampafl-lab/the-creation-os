from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.contracts import MemoryCandidate, MemorySourceType
from app.models.entities import Conversation, Inception, Message, Mission, Task
from app.models.execution import AgentExecution, CapabilityInvocation


class MemoryProvenanceError(ValueError):
    pass


class MemoryPolicy:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def validate_provenance(self, creator_id: str, candidate: MemoryCandidate) -> None:
        source_id = candidate.source_id
        source_type = candidate.source_type

        if source_type is MemorySourceType.CONVERSATION:
            found = await self.session.scalar(
                select(Conversation.id).where(Conversation.id == source_id, Conversation.creator_id == creator_id)
            )
        elif source_type is MemorySourceType.MESSAGE:
            found = await self.session.scalar(
                select(Message.id)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Message.id == source_id, Conversation.creator_id == creator_id)
            )
        elif source_type is MemorySourceType.INCEPTION:
            found = await self.session.scalar(
                select(Inception.id)
                .join(Conversation, Conversation.id == Inception.conversation_id)
                .where(Inception.id == source_id, Conversation.creator_id == creator_id)
            )
        elif source_type is MemorySourceType.MISSION:
            found = await self.session.scalar(
                select(Mission.id).where(Mission.id == source_id, Mission.creator_id == creator_id)
            )
        elif source_type is MemorySourceType.TASK:
            found = await self.session.scalar(
                select(Task.id)
                .join(Mission, Mission.id == Task.mission_id)
                .where(Task.id == source_id, Mission.creator_id == creator_id)
            )
        elif source_type is MemorySourceType.AGENT_EXECUTION:
            found = await self.session.scalar(
                select(AgentExecution.id)
                .join(Task, Task.id == AgentExecution.task_id)
                .join(Mission, Mission.id == Task.mission_id)
                .where(AgentExecution.id == source_id, Mission.creator_id == creator_id)
            )
        elif source_type is MemorySourceType.CAPABILITY_INVOCATION:
            found = await self.session.scalar(
                select(CapabilityInvocation.id)
                .join(Mission, Mission.id == CapabilityInvocation.mission_id)
                .where(CapabilityInvocation.id == source_id, Mission.creator_id == creator_id)
            )
        else:  # defensive guard for future enum expansion
            found = None

        if found is None:
            raise MemoryProvenanceError("memory provenance source does not exist in Creator scope")
