from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.sophia import SophiaUnderstandingType, build_understanding


def god_interaction(interaction_type: str = "POTENTIAL"):
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        interaction_type=interaction_type,
        request_payload={
            "message": "  Criar   sistema  ",
            "idempotency_key": "sophia-key",
            "request_fingerprint": "a" * 64,
        },
        potential_detected=interaction_type == "POTENTIAL",
        fingerprint="b" * 64,
    )


def test_sophia_understanding_is_deterministic_and_non_executing():
    interaction = god_interaction()

    first = build_understanding(interaction)
    second = build_understanding(interaction)

    assert first == second
    assert first.understanding_type == SophiaUnderstandingType.POTENTIAL_UNDERSTANDING
    assert len(first.source_fingerprint) == 64
    assert len(first.fingerprint) == 64
    assert first.payload["normalized_message"] == "criar sistema"
    assert first.payload["boundaries"] == {
        "decides": False,
        "manifests": False,
        "executes": False,
        "creates_inception": False,
        "creates_mission": False,
    }


def test_sophia_maps_all_god_interaction_types():
    assert build_understanding(god_interaction("DIRECT_RESPONSE")).understanding_type == (
        SophiaUnderstandingType.DIRECT_UNDERSTANDING
    )
    assert build_understanding(god_interaction("INFORMATIONAL")).understanding_type == (
        SophiaUnderstandingType.INFORMATIONAL_UNDERSTANDING
    )
    assert build_understanding(god_interaction("POTENTIAL")).understanding_type == (
        SophiaUnderstandingType.POTENTIAL_UNDERSTANDING
    )
    assert build_understanding(god_interaction("UNSUPPORTED")).understanding_type == (
        SophiaUnderstandingType.UNSUPPORTED_UNDERSTANDING
    )
