from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.domain import Actor, ConversationStatus, InvalidOrigin, require_creator
from app.inference.contracts import InferenceRequest, ModelRequirements
from app.inference.router import ModelRouter
from app.models.entities import Conversation, Message
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


class DeusConversationService:
    def __init__(
        self,
        repository: DomainRepository,
        router: ModelRouter,
        *,
        provider: str,
        model: str,
        fallback_providers: Sequence[str] = (),
    ) -> None:
        self.repo = repository
        self.router = router
        self.provider = provider
        self.model = model
        self.fallback_providers = [str(name) for name in fallback_providers]

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
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({
            "role": "assistant" if item.role == "deus" else "user",
            "content": item.content,
        } for item in history)

        inference = await self.router.generate(InferenceRequest(
            messages=messages,
            # Each provider serves its own default model, so pinning the primary model
            # would make the fallbacks unroutable.
            model=None if self.fallback_providers else self.model,
            requirements=ModelRequirements(
                preferred_provider=self.provider,
                fallback_providers=self.fallback_providers,
            ),
            metadata={
                "conversation_id": conversation_id,
                "creator_id": actor.id,
                "route": "deus",
                "cache_sensitivity": "PRIVATE",
                "cache_tags": [f"conversation:{conversation_id}", "route:deus"],
                "tool_state_class": "read_only",
            },
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
        )
