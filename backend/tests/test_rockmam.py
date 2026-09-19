from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.rockmam import RockmamResult, build_assessment


def understanding(understanding_type: str, payload_overrides: dict | None = None):
    payload = {
        "schema_version": "1.0",
        "understanding_version": "v0.8.0",
        "source": "DEUS",
        "god_interaction_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "interaction_type": "POTENTIAL",
        "understanding_type": understanding_type,
        "normalized_message": "criar sistema",
        "potential_detected": understanding_type == "POTENTIAL_UNDERSTANDING",
        "boundaries": {
            "decides": False,
            "manifests": False,
            "executes": False,
            "creates_inception": False,
            "creates_mission": False,
        },
        "signals": {
            "direct_response": understanding_type == "DIRECT_UNDERSTANDING",
            "informational": understanding_type == "INFORMATIONAL_UNDERSTANDING",
            "potential": understanding_type == "POTENTIAL_UNDERSTANDING",
            "unsupported": understanding_type == "UNSUPPORTED_UNDERSTANDING",
        },
    }
    payload.update(payload_overrides or {})
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        conversation_id=payload["conversation_id"],
        understanding_type=understanding_type,
        understanding_payload=payload,
        source_fingerprint="a" * 64,
        understanding_fingerprint="b" * 64,
    )


def test_rockmam_assessment_is_deterministic_and_creator_gated_for_potential():
    item = understanding("POTENTIAL_UNDERSTANDING")

    first = build_assessment(item)
    second = build_assessment(item)

    assert first == second
    assert first.result == RockmamResult.REQUIRES_CREATOR
    assert first.payload["technical_viability"] is True
    assert first.payload["capabilities"]["requires_creator_direction"] is True
    assert first.payload["blockers"] == []
    assert len(first.source_fingerprint) == 64
    assert len(first.fingerprint) == 64


def test_rockmam_result_mapping_is_limited_to_allowed_results():
    assert build_assessment(understanding("DIRECT_UNDERSTANDING")).result == RockmamResult.VIABLE
    assert build_assessment(understanding("INFORMATIONAL_UNDERSTANDING")).result == RockmamResult.VIABLE
    assert build_assessment(understanding("POTENTIAL_UNDERSTANDING")).result == RockmamResult.REQUIRES_CREATOR
    assert build_assessment(understanding("UNSUPPORTED_UNDERSTANDING")).result == RockmamResult.NOT_VIABLE


def test_rockmam_blocks_incomplete_or_boundary_violating_understanding():
    incomplete = understanding("DIRECT_UNDERSTANDING", {"signals": None})
    del incomplete.understanding_payload["signals"]
    violating = understanding("DIRECT_UNDERSTANDING", {"boundaries": {"decides": True}})

    assert build_assessment(incomplete).result == RockmamResult.NOT_VIABLE
    assert build_assessment(violating).result == RockmamResult.NOT_VIABLE
