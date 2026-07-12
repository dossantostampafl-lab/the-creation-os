from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import ConversationStatus, InceptionStatus, InvalidOrigin, MissionStatus
from app.models.entities import Chronicle, Conversation, Inception, Message, Mission

T = TypeVar("T")

SENSITIVE_KEYS = {"token", "password", "secret", "authorization", "cookie", "api_key", "apikey", "access_token", "refresh_token"}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if k.lower().replace("-", "_") not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def canonical_event(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def event_hash(event: dict[str, Any], previous_hash: str | None) -> str:
    return hashlib.sha256((canonical_event(event) + (previous_hash or "")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChronicleIntegrity:
    valid: bool
    first_invalid_event_id: str | None = None
    reason: str | None = None


class DomainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, model: type[T], entity_id: str) -> T | None:
        return await self.session.get(model, entity_id)

    async def get_for_update(self, model: type[T], entity_id: str) -> T | None:
        stmt = select(model).where(getattr(model, 'id') == entity_id).with_for_update()
        return await self.session.scalar(cast(Any, stmt))

    async def list_for_creator(self, model: type[T], creator_id: str) -> list[T]:
        if model is Inception:
            stmt = select(model).join(Conversation).where(getattr(Conversation, 'creator_id') == creator_id)
        else:
            stmt = select(model).where(getattr(model, 'creator_id') == creator_id)
        # SQLAlchemy typing is complex here; cast the result to the expected list type
        return cast(list[T], (await self.session.scalars(cast(Any, stmt.order_by(getattr(model, 'id'))))).all())

    async def add(self, entity: T) -> T:
        required_initial = {Conversation: ConversationStatus.ACTIVE.value,
                            Inception: InceptionStatus.PROPOSED.value,
                            Mission: MissionStatus.DRAFTED.value}
        expected = required_initial.get(type(entity))
        if expected is not None and entity not in self.session and getattr(entity, "status", None) != expected:
            raise InvalidOrigin(f"{type(entity).__name__} must be created in {expected} state")
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def source_message(self, conversation_id: str, message_id: str) -> Message | None:
        return await self.session.scalar(select(Message).where(
            Message.id == message_id, Message.conversation_id == conversation_id
        ))

    async def mission_for_inception(self, inception_id: str, lock: bool = False) -> Mission | None:
        stmt = select(Mission).where(Mission.inception_id == inception_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def owner_id(self, model: type, entity_id: str) -> str | None:
        if model is Inception:
            stmt = select(getattr(Conversation, 'creator_id')).join(
                Inception, Inception.conversation_id == Conversation.id).where(Inception.id == entity_id)
            return await self.session.scalar(cast(Any, stmt))
        stmt = select(getattr(model, 'creator_id')).where(getattr(model, 'id') == entity_id)
        return await self.session.scalar(cast(Any, stmt))

    async def add_event(
        self, event_type: str, aggregate_type: str, aggregate_id: str | None,
        actor_id: str, actor_role: str, correlation_id: str, payload: dict[str, Any] | None = None,
    ) -> Chronicle:
        # Serializes the empty-chain case as well as normal appends on PostgreSQL.
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            await self.session.execute(text("SELECT pg_advisory_xact_lock(84739201)"))
        previous_event = await self.session.scalar(select(Chronicle).order_by(Chronicle.position.desc()).limit(1))
        previous = previous_event.payload_hash if previous_event else None
        position = (previous_event.position + 1) if previous_event else 1
        safe = sanitize(payload or {})
        created_at = datetime.now(timezone.utc)
        event_id = str(uuid.uuid4())
        material = {"event_id": event_id, "position": position, "event_type": event_type,
                    "aggregate_type": aggregate_type, "aggregate_id": aggregate_id, "actor_id": actor_id,
                    "actor_role": actor_role, "correlation_id": correlation_id, "payload": safe,
                    "created_at": created_at.isoformat()}
        event = Chronicle(
            event_id=event_id, position=position, correlation_id=correlation_id, actor_type=actor_role,
            actor_role=actor_role, actor_id=actor_id, event_type=event_type,
            aggregate_type=aggregate_type, aggregate_id=aggregate_id, payload_json=safe,
            payload_hash=event_hash(material, previous), previous_hash=previous, created_at=created_at,
        )
        return await self.add(event)

    async def verify_chronicle(self) -> ChronicleIntegrity:
        events = list((await self.session.scalars(select(Chronicle).order_by(Chronicle.position))).all())
        previous = None
        expected_position = 1
        for item in events:
            if item.position != expected_position:
                return ChronicleIntegrity(False, item.event_id, "broken sequence")
            if item.previous_hash != previous:
                return ChronicleIntegrity(False, item.event_id, "invalid previous_hash")
            material = {"event_id": item.event_id, "position": item.position, "event_type": item.event_type,
                        "aggregate_type": item.aggregate_type, "aggregate_id": item.aggregate_id,
                        "actor_id": item.actor_id, "actor_role": item.actor_role,
                        "correlation_id": item.correlation_id, "payload": item.payload_json,
                        "created_at": item.created_at.isoformat()}
            if event_hash(material, previous) != item.payload_hash:
                return ChronicleIntegrity(False, item.event_id, "invalid event hash")
            previous = item.payload_hash
            expected_position += 1
        return ChronicleIntegrity(True)

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def rollback(self) -> None:
        await self.session.rollback()
