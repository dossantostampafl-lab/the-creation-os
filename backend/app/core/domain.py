from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DomainError(Exception):
    """Base error for rejected domain operations."""


class InvalidStateTransition(DomainError):
    def __init__(self, aggregate: str, current: str, target: str) -> None:
        super().__init__(f"Invalid {aggregate} transition: {current} -> {target}")


class AuthorizationDenied(DomainError):
    pass


class InvalidOrigin(DomainError):
    pass


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class InceptionStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_CREATOR_DECISION = "awaiting_creator_decision"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class MissionStatus(StrEnum):
    DRAFTED = "drafted"
    PLANNED = "planned"
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    DISTRIBUTED = "distributed"
    EXECUTING = "executing"
    MANIFESTED = "manifested"
    FAILED = "failed"
    CANCELLED = "cancelled"


TRANSITIONS: dict[str, dict[StrEnum, set[StrEnum]]] = {
    "conversation": {
        ConversationStatus.ACTIVE: {ConversationStatus.CLOSED},
        ConversationStatus.CLOSED: {ConversationStatus.ARCHIVED},
        ConversationStatus.ARCHIVED: set(),
    },
    "inception": {
        InceptionStatus.PROPOSED: {InceptionStatus.AWAITING_CREATOR_DECISION, InceptionStatus.CANCELLED},
        InceptionStatus.AWAITING_CREATOR_DECISION: {
            InceptionStatus.APPROVED, InceptionStatus.REJECTED, InceptionStatus.CANCELLED
        },
        InceptionStatus.APPROVED: {InceptionStatus.CANCELLED},
        InceptionStatus.REJECTED: set(),
        InceptionStatus.CANCELLED: set(),
    },
    "mission": {
        MissionStatus.DRAFTED: {MissionStatus.PLANNED, MissionStatus.CANCELLED},
        MissionStatus.PLANNED: {MissionStatus.VALIDATED, MissionStatus.CANCELLED},
        MissionStatus.VALIDATED: {MissionStatus.AUTHORIZED, MissionStatus.CANCELLED},
        MissionStatus.AUTHORIZED: {MissionStatus.DISTRIBUTED, MissionStatus.CANCELLED},
        MissionStatus.DISTRIBUTED: {MissionStatus.EXECUTING, MissionStatus.CANCELLED},
        MissionStatus.EXECUTING: {MissionStatus.MANIFESTED, MissionStatus.FAILED, MissionStatus.CANCELLED},
        MissionStatus.MANIFESTED: set(), MissionStatus.FAILED: set(), MissionStatus.CANCELLED: set(),
    },
}


def transition(aggregate: str, current: StrEnum, target: StrEnum) -> str:
    transitions_for_agg = TRANSITIONS[aggregate]
    if target not in transitions_for_agg.get(current, set()):
        raise InvalidStateTransition(aggregate, current.value, target.value)
    return target.value


@dataclass(frozen=True)
class Actor:
    id: str
    role: str


def require_creator(actor: Actor, action: str) -> None:
    if actor.role != "creator":
        raise AuthorizationDenied(f"Only Creator may {action}")


def require_malkuth_authorized(status: str) -> None:
    if status not in {MissionStatus.AUTHORIZED.value, MissionStatus.DISTRIBUTED.value, MissionStatus.EXECUTING.value}:
        raise AuthorizationDenied("Malkuth cannot manifest an unauthorized mission")


def request_total_destruction(actor: Actor) -> None:
    require_creator(actor, "request total destruction")
    raise AuthorizationDenied("Total destruction is disabled and has no public route")
