from __future__ import annotations

import uuid

from app.core.god import GodInteractionType, build_god_interaction, classify_message


def test_god_classification_is_deterministic_and_limited_to_contract():
    assert classify_message("Ola GOD") == GodInteractionType.DIRECT_RESPONSE
    assert classify_message("Nota: lembre este contexto") == GodInteractionType.INFORMATIONAL
    assert classify_message("Quero criar um projeto novo") == GodInteractionType.POTENTIAL
    assert classify_message("Execute agent e chame Malkuth") == GodInteractionType.UNSUPPORTED


def test_god_interaction_fingerprint_is_deterministic():
    conversation_id = str(uuid.uuid4())
    first = build_god_interaction(conversation_id, "Criar sistema interno", "same-key")
    second = build_god_interaction(conversation_id, "  criar   sistema interno  ", "same-key")

    assert first == second
    assert first.interaction_type == GodInteractionType.POTENTIAL
    assert first.potential_detected
    assert first.next_action == "creator_may_request_trinity_analysis"
    assert len(first.request_fingerprint) == 64
    assert len(first.fingerprint) == 64
