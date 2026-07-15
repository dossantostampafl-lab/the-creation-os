from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.god import normalize_creator_message
from app.models.god import GodConversationInteraction

SOPHIA_UNDERSTANDING_VERSION = "v0.8.0"


class SophiaUnderstandingType(StrEnum):
    DIRECT_UNDERSTANDING = "DIRECT_UNDERSTANDING"
    INFORMATIONAL_UNDERSTANDING = "INFORMATIONAL_UNDERSTANDING"
    POTENTIAL_UNDERSTANDING = "POTENTIAL_UNDERSTANDING"
    UNSUPPORTED_UNDERSTANDING = "UNSUPPORTED_UNDERSTANDING"


@dataclass(frozen=True)
class SophiaUnderstandingDocument:
    understanding_type: SophiaUnderstandingType
    payload: dict[str, Any]
    source_fingerprint: str
    fingerprint: str


UNDERSTANDING_BY_GOD_TYPE = {
    "DIRECT_RESPONSE": SophiaUnderstandingType.DIRECT_UNDERSTANDING,
    "INFORMATIONAL": SophiaUnderstandingType.INFORMATIONAL_UNDERSTANDING,
    "POTENTIAL": SophiaUnderstandingType.POTENTIAL_UNDERSTANDING,
    "UNSUPPORTED": SophiaUnderstandingType.UNSUPPORTED_UNDERSTANDING,
}


def deterministic_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_understanding(interaction: GodConversationInteraction) -> SophiaUnderstandingDocument:
    understanding_type = UNDERSTANDING_BY_GOD_TYPE[interaction.interaction_type]
    creator_message = str(interaction.request_payload.get("message", ""))
    normalized_message = normalize_creator_message(creator_message)
    request_fingerprint = str(interaction.request_payload.get("request_fingerprint", ""))
    source_fingerprint = deterministic_fingerprint(
        {
            "god_interaction_id": interaction.id,
            "god_fingerprint": interaction.fingerprint,
            "request_fingerprint": request_fingerprint,
            "interaction_type": interaction.interaction_type,
        }
    )
    payload = {
        "schema_version": "1.0",
        "understanding_version": SOPHIA_UNDERSTANDING_VERSION,
        "source": "GOD",
        "god_interaction_id": interaction.id,
        "conversation_id": interaction.conversation_id,
        "interaction_type": interaction.interaction_type,
        "understanding_type": understanding_type.value,
        "normalized_message": normalized_message,
        "potential_detected": interaction.potential_detected,
        "boundaries": {
            "decides": False,
            "manifests": False,
            "executes": False,
            "creates_inception": False,
            "creates_mission": False,
        },
        "signals": {
            "direct_response": interaction.interaction_type == "DIRECT_RESPONSE",
            "informational": interaction.interaction_type == "INFORMATIONAL",
            "potential": interaction.interaction_type == "POTENTIAL",
            "unsupported": interaction.interaction_type == "UNSUPPORTED",
        },
    }
    fingerprint = deterministic_fingerprint(
        {
            "schema_version": "1.0",
            "understanding_version": SOPHIA_UNDERSTANDING_VERSION,
            "source_fingerprint": source_fingerprint,
            "payload": payload,
        }
    )
    return SophiaUnderstandingDocument(
        understanding_type=understanding_type,
        payload=payload,
        source_fingerprint=source_fingerprint,
        fingerprint=fingerprint,
    )
