import pytest

from app.core.domain import (
    Actor,
    AuthorizationDenied,
    ConversationStatus,
    InceptionStatus,
    InvalidOrigin,
    InvalidStateTransition,
    MissionStatus,
    request_total_destruction,
    require_creator,
    require_malkuth_authorized,
    transition,
)
from app.models.entities import Mission
from app.repositories.domain import DomainRepository, event_hash, sanitize


@pytest.fixture
def creator():
    return Actor("00000000-0000-0000-0000-000000000001", "creator")


@pytest.fixture
def user():
    return Actor("00000000-0000-0000-0000-000000000002", "user")


@pytest.mark.parametrize("action", ["control GOD", "approve Inception", "reject Inception", "authorize Mission"])
def test_common_user_cannot_perform_creator_actions(user, action):
    with pytest.raises(AuthorizationDenied):
        require_creator(user, action)


@pytest.mark.parametrize("action", ["control GOD", "approve Inception", "reject Inception", "authorize Mission"])
def test_creator_can_perform_reserved_actions(creator, action):
    require_creator(creator, action)


def test_common_user_cannot_request_total_destruction(user):
    with pytest.raises(AuthorizationDenied):
        request_total_destruction(user)


def test_total_destruction_is_disabled_even_for_creator(creator):
    with pytest.raises(AuthorizationDenied, match="disabled"):
        request_total_destruction(creator)


@pytest.mark.parametrize("status", [MissionStatus.DRAFTED.value, MissionStatus.PLANNED.value,
                                     MissionStatus.VALIDATED.value, MissionStatus.CANCELLED.value])
def test_malkuth_cannot_execute_unauthorized_mission(status):
    with pytest.raises(AuthorizationDenied):
        require_malkuth_authorized(status)


def test_invalid_state_transition_returns_specific_domain_error():
    with pytest.raises(InvalidStateTransition):
        transition("inception", InceptionStatus.REJECTED, InceptionStatus.APPROVED)


def test_inception_pending_cannot_skip_to_manifestation_or_approval_from_proposed():
    with pytest.raises(InvalidStateTransition):
        transition("inception", InceptionStatus.PROPOSED, InceptionStatus.APPROVED)


def test_rejected_inception_is_terminal():
    with pytest.raises(InvalidStateTransition):
        transition("inception", InceptionStatus.REJECTED, InceptionStatus.CANCELLED)


def test_mission_requires_ordered_plan_validate_authorize_flow():
    with pytest.raises(InvalidStateTransition):
        transition("mission", MissionStatus.DRAFTED, MissionStatus.AUTHORIZED)
    assert transition("mission", MissionStatus.DRAFTED, MissionStatus.PLANNED) == "planned"
    assert transition("mission", MissionStatus.PLANNED, MissionStatus.VALIDATED) == "validated"
    assert transition("mission", MissionStatus.VALIDATED, MissionStatus.AUTHORIZED) == "authorized"


def test_conversation_state_machine():
    assert transition("conversation", ConversationStatus.ACTIVE, ConversationStatus.CLOSED) == "closed"
    with pytest.raises(InvalidStateTransition):
        transition("conversation", ConversationStatus.ACTIVE, ConversationStatus.ARCHIVED)


def test_recursive_chronicle_sanitization():
    value = sanitize({"safe": 1, "nested": {"password": "x", "API-Key": "y", "ok": True},
                      "items": [{"authorization": "Bearer secret", "visible": "yes"}], "cookie": "bad"})
    assert value == {"safe": 1, "nested": {"ok": True}, "items": [{"visible": "yes"}]}


def test_chronicle_hash_is_deterministic():
    event = {"b": 2, "a": {"z": 1}}
    assert event_hash(event, "previous") == event_hash({"a": {"z": 1}, "b": 2}, "previous")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["distributed", "executing", "manifested", "arbitrary"])
async def test_generic_repository_rejects_non_initial_mission_status(status):
    class Session:
        def __contains__(self, item):
            return False

    repository = DomainRepository(Session())
    mission = Mission(inception_id="i", creator_id="c", title="x", objective="x",
                      status=status, authorization_json={})
    with pytest.raises(InvalidOrigin):
        await repository.add(mission)
