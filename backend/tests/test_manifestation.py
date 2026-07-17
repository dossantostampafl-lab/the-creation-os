from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.manifestation import ManifestationState, build_manifestation, is_valid_fingerprint


def approved_decision():
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        mission_id=str(uuid.uuid4()),
        decision="APPROVED",
        consolidation_fingerprint="a" * 64,
    )


def test_manifestation_is_deterministic_internal_record():
    decision = approved_decision()

    first = build_manifestation(decision)
    second = build_manifestation(decision)

    assert first == second
    assert first.state == ManifestationState.MANIFESTED
    assert len(first.fingerprint) == 64
    assert first.payload == {
        "schema_version": "1.0",
        "mission_id": decision.mission_id,
        "decision_id": decision.id,
        "decision": "APPROVED",
        "decision_fingerprint": decision.consolidation_fingerprint,
        "manifestation_type": "internal_record",
    }
    assert first.audit_metadata["validation"] == {
        "decision_exists": True,
        "decision_approved": True,
        "fingerprint_valid": True,
        "previous_manifestation_absent": True,
    }


def test_fingerprint_validation_accepts_only_sha256_hex():
    assert is_valid_fingerprint("a" * 64)
    assert is_valid_fingerprint("A" * 64)
    assert not is_valid_fingerprint(None)
    assert not is_valid_fingerprint("a" * 63)
    assert not is_valid_fingerprint("z" * 64)
