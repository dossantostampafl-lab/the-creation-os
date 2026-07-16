from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

GOD_CONVERSATION_POLICY_VERSION = "v0.7.0"


class GodInteractionType(StrEnum):
    DIRECT_RESPONSE = "DIRECT_RESPONSE"
    INFORMATIONAL = "INFORMATIONAL"
    POTENTIAL = "POTENTIAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class GodInteractionDocument:
    interaction_type: GodInteractionType
    reply: dict[str, Any]
    potential_detected: bool
    next_action: str
    request_fingerprint: str
    fingerprint: str


UNSUPPORTED_TERMS = (
    "agent",
    "agente",
    "central core",
    "chamar creator",
    "creator interface",
    "email",
    "execute agent",
    "github",
    "internet",
    "malkuth",
    "manifest",
    "manifestar",
    "missiondecision",
    "rockmam",
    "slack",
    "sophia",
    "tree core",
    "whatsapp",
)

INFORMATIONAL_TERMS = (
    "contexto",
    "fyi",
    "informacao",
    "lembre",
    "lembrar",
    "nota",
    "observe",
    "registro",
)

POTENTIAL_TERMS = (
    "analisar",
    "analise",
    "build",
    "construir",
    "criar",
    "implementar",
    "missao",
    "objetivo",
    "planejar",
    "projeto",
    "sistema",
)


def normalize_creator_message(message: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", message) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.strip().casefold())


def classify_message(message: str) -> GodInteractionType:
    normalized = normalize_creator_message(message)
    if any(term in normalized for term in UNSUPPORTED_TERMS):
        return GodInteractionType.UNSUPPORTED
    if any(term in normalized for term in INFORMATIONAL_TERMS):
        return GodInteractionType.INFORMATIONAL
    if any(term in normalized for term in POTENTIAL_TERMS):
        return GodInteractionType.POTENTIAL
    return GodInteractionType.DIRECT_RESPONSE


def build_reply(interaction_type: GodInteractionType) -> tuple[dict[str, Any], str, bool]:
    if interaction_type == GodInteractionType.INFORMATIONAL:
        return (
            {
                "message": "Informacao registrada na conversa sem iniciar fluxo de missao.",
                "policy_version": GOD_CONVERSATION_POLICY_VERSION,
            },
            "record_context",
            False,
        )
    if interaction_type == GodInteractionType.POTENTIAL:
        return (
            {
                "message": (
                    "Potencial identificado. A proxima acao permitida e solicitar analise da Trindade; "
                    "nenhuma Inception foi criada automaticamente."
                ),
                "policy_version": GOD_CONVERSATION_POLICY_VERSION,
            },
            "creator_may_request_trinity_analysis",
            True,
        )
    if interaction_type == GodInteractionType.UNSUPPORTED:
        return (
            {
                "message": "Solicitacao fora do contrato atual de GOD. Nenhuma acao operacional foi executada.",
                "policy_version": GOD_CONVERSATION_POLICY_VERSION,
            },
            "unsupported_no_action",
            False,
        )
    return (
        {
            "message": "GOD registrou sua mensagem e pode responder diretamente dentro do contrato atual.",
            "policy_version": GOD_CONVERSATION_POLICY_VERSION,
        },
        "continue_conversation",
        False,
    )


def deterministic_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_request_fingerprint(conversation_id: str, message: str, idempotency_key: str) -> str:
    return deterministic_fingerprint(
        {
            "schema_version": "1.0",
            "policy_version": GOD_CONVERSATION_POLICY_VERSION,
            "conversation_id": conversation_id,
            "idempotency_key": idempotency_key,
            "message": normalize_creator_message(message),
        }
    )


def build_god_interaction(
    conversation_id: str,
    message: str,
    idempotency_key: str,
    memory_context: list[dict[str, Any]] | None = None,
) -> GodInteractionDocument:
    interaction_type = classify_message(message)
    reply, next_action, potential_detected = build_reply(interaction_type)
    resolved_memory_context = memory_context or []
    request_fingerprint = canonical_request_fingerprint(conversation_id, message, idempotency_key)
    fingerprint_payload = {
        "schema_version": "1.0",
        "policy_version": GOD_CONVERSATION_POLICY_VERSION,
        "conversation_id": conversation_id,
        "idempotency_key": idempotency_key,
        "request_fingerprint": request_fingerprint,
        "memory_context": resolved_memory_context,
        "interaction_type": interaction_type.value,
        "reply": reply,
        "potential_detected": potential_detected,
        "next_action": next_action,
    }
    return GodInteractionDocument(
        interaction_type=interaction_type,
        reply=reply,
        potential_detected=potential_detected,
        next_action=next_action,
        request_fingerprint=request_fingerprint,
        fingerprint=deterministic_fingerprint(fingerprint_payload),
    )
