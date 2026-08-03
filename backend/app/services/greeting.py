from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.domain import Actor
from app.core.god import format_system_query_reply
from app.models.entities import Message
from app.repositories.god import GodConversationRepository
from app.services.god import GodConversationService

# Lote: DEUS inicia conversa automaticamente após login. Access tokens are
# stateless JWTs (no server-side session record to key off of — see
# app/services/auth.py), so "first load of a new token session" isn't
# something the backend can observe directly. A time window keyed off the
# most recent greeting's own timestamp needs no new schema/session tracking
# and keeps a reload or a quick re-login from spamming the conversation.
# 30 minutes: long enough that refreshing the page a few times mid-session
# doesn't repeat it, short enough that returning later in the same day still
# gets a genuinely fresh snapshot. See ARCHITECTURE.md.
LOGIN_GREETING_COOLDOWN = timedelta(minutes=30)

GREETING_SNAPSHOT_TRIGGER = "estado do sistema"


async def maybe_send_login_greeting(repository: GodConversationRepository, actor: Actor, correlation_id: str) -> str:
    """Called from POST /auth/login only (never /auth/refresh). Ensures the
    Creator's anchor DEUS conversation exists and, unless a greeting was
    already sent within LOGIN_GREETING_COOLDOWN, appends a proactive,
    contextual GOD message summarizing real system state — reusing
    GodConversationService.system_snapshot()/format_system_query_reply(),
    the same resolution SYSTEM_QUERY already uses, not a re-derived query.
    Always returns the anchor conversation id, greeted or not, so the
    frontend has somewhere to read the conversation from either way."""
    conversation_id = await repository.anchor_conversation_id(actor.id)
    latest = await repository.latest_greeting_message(conversation_id)
    now = datetime.now(timezone.utc)
    if latest is not None and (now - latest.created_at) < LOGIN_GREETING_COOLDOWN:
        return conversation_id

    god_service = GodConversationService(repository)
    system_snapshot = await god_service.system_snapshot(actor, GREETING_SNAPSHOT_TRIGGER)
    summary = format_system_query_reply(system_snapshot)
    greeting_text = f"DEUS esta presente. Bem-vindo de volta, Criador. {summary}"

    await repository.add_message(
        Message(
            conversation_id=conversation_id,
            actor_id="god",
            role="god",
            content=greeting_text,
            route="god",
            correlation_id=correlation_id,
            metadata_json={"greeting": True, "system_snapshot": system_snapshot},
        )
    )
    await repository.add_event(
        "login_greeting_sent",
        "conversation",
        conversation_id,
        actor.id,
        actor.role,
        correlation_id,
        {"system_snapshot": system_snapshot},
    )
    await repository.commit()
    return conversation_id
