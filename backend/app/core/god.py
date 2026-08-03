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
    SYSTEM_QUERY = "SYSTEM_QUERY"
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

# SYSTEM_QUERY: read-only questions about real, live system state. Checked
# before INFORMATIONAL/POTENTIAL (several of these phrases contain words like
# "missao"/"sistema" that would otherwise match POTENTIAL_TERMS) and after
# UNSUPPORTED (an unsupported request always wins, same as before). Each topic
# key doubles as the lookup used by GodConversationService to know which real
# data to fetch — see classify_system_query_topic() below.
SYSTEM_QUERY_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "pulse": (
        "pulse",
        "pulso do sistema",
        "saude do sistema",
        "batimento do sistema",
    ),
    "missions": (
        "quantas missoes",
        "missoes existem",
        "estado das missoes",
        "status das missoes",
        "missoes em andamento",
    ),
    "inceptions": (
        "inceptions pendentes",
        "quantas inceptions",
        "inception pendente",
        "inceptions em aberto",
    ),
    "memory": (
        "quanta memoria",
        "memoria armazenada",
        "itens de memoria",
        "memoria consolidada",
    ),
    "universes": (
        "quantos universos",
        "universos ativos",
        "universos existem",
    ),
    "agents": (
        "agentes disponiveis",
        "quantos agentes",
        "agentes ativos",
        "agentes online",
    ),
    "general": (
        "estado do sistema",
        "status do sistema",
        "como esta o sistema",
        "situacao do sistema",
    ),
}

SYSTEM_QUERY_TERMS: tuple[str, ...] = tuple(
    term for terms in SYSTEM_QUERY_TOPIC_TERMS.values() for term in terms
)


def normalize_creator_message(message: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", message) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.strip().casefold())


def classify_message(message: str) -> GodInteractionType:
    normalized = normalize_creator_message(message)
    # Narrow, deliberate exception: every phrase in the "agents" SYSTEM_QUERY
    # topic contains "agente(s)", which is itself an UNSUPPORTED_TERMS entry
    # (it blocks operational commands like "execute agent"). A read-only
    # "how many agents are available" question is a different intent that
    # happens to share the word, not a weakening of that boundary — so only
    # these exact, enumerated read-only phrases are checked ahead of
    # UNSUPPORTED. No other SYSTEM_QUERY topic collides with any
    # UNSUPPORTED_TERMS entry, so their relative order (after UNSUPPORTED,
    # same as before this lote) is unchanged.
    if any(term in normalized for term in SYSTEM_QUERY_TOPIC_TERMS["agents"]):
        return GodInteractionType.SYSTEM_QUERY
    if any(term in normalized for term in UNSUPPORTED_TERMS):
        return GodInteractionType.UNSUPPORTED
    if any(term in normalized for term in SYSTEM_QUERY_TERMS):
        return GodInteractionType.SYSTEM_QUERY
    if any(term in normalized for term in INFORMATIONAL_TERMS):
        return GodInteractionType.INFORMATIONAL
    if any(term in normalized for term in POTENTIAL_TERMS):
        return GodInteractionType.POTENTIAL
    return GodInteractionType.DIRECT_RESPONSE


def classify_system_query_topic(message: str) -> str:
    """Which of SYSTEM_QUERY_TOPIC_TERMS' keys the message matched — used by
    GodConversationService to decide which real data to fetch. Only meaningful
    when classify_message() already returned SYSTEM_QUERY; defaults to
    "general" if called on a message that happens to match no specific topic."""
    normalized = normalize_creator_message(message)
    for topic, terms in SYSTEM_QUERY_TOPIC_TERMS.items():
        if any(term in normalized for term in terms):
            return topic
    return "general"


def format_system_query_reply(system_snapshot: dict[str, Any] | None) -> str:
    if not system_snapshot:
        return "Nao consegui consultar o estado do sistema agora."
    topic = system_snapshot.get("topic")
    data = system_snapshot.get("data", {})
    if topic == "pulse":
        return (
            f"Pulse: status={data.get('status')}, banco={data.get('database', {}).get('status')}, "
            f"redis={data.get('redis', {}).get('status')}, "
            f"cadeia de Chronicles valida={data.get('chronicles_chain', {}).get('valid')}, "
            f"erros recentes={data.get('error_count')}."
        )
    if topic == "missions":
        return f"Missoes: {data.get('running')} em andamento, {data.get('total')} no total."
    if topic == "inceptions":
        return f"Inceptions pendentes: {data.get('pending')}."
    if topic == "memory":
        return (
            f"Memoria: {data.get('creator_memory_items')} itens de memoria do Criador, "
            f"{data.get('conscious_memory_items')} itens de memoria consolidada."
        )
    if topic == "universes":
        return f"Universos: {data.get('active')} ativos de {data.get('total')} no total."
    if topic == "agents":
        return f"Agentes: {data.get('available')} disponiveis de {data.get('total')} no total."
    return (
        f"Estado geral: {data.get('running_missions')} missoes em andamento, "
        f"{data.get('pending_inceptions')} Inceptions pendentes, "
        f"{data.get('active_universes')} Universos ativos, "
        f"{data.get('active_agents')} agentes ativos."
    )


def build_reply(
    interaction_type: GodInteractionType,
    message: str,
    system_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, bool]:
    normalized = normalize_creator_message(message)
    summary = normalized[:180] if normalized else "mensagem recebida"
    if interaction_type == GodInteractionType.SYSTEM_QUERY:
        return (
            {
                "message": format_system_query_reply(system_snapshot),
                "policy_version": GOD_CONVERSATION_POLICY_VERSION,
                "system_query": system_snapshot,
            },
            "system_query_answered",
            False,
        )
    if interaction_type == GodInteractionType.INFORMATIONAL:
        return (
            {
                "message": f"Registrei o contexto informado: {summary}. Nenhuma missao ou Inception foi criada automaticamente.",
                "policy_version": GOD_CONVERSATION_POLICY_VERSION,
            },
            "record_context",
            False,
        )
    if interaction_type == GodInteractionType.POTENTIAL:
        return (
            {
                "message": (
                    f"Identifiquei potencial relacionado a: {summary}. Posso preparar a analise da Trindade para o Criador decidir; "
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
                "message": f"A solicitacao excede o contrato atual de DEUS: {summary}. Nenhuma acao operacional foi executada.",
                "policy_version": GOD_CONVERSATION_POLICY_VERSION,
            },
            "unsupported_no_action",
            False,
        )
    return (
        {
            "message": f"Estou presente. Registrei: {summary}. Posso continuar a conversa ou aguardar uma decisao do Criador.",
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
    system_snapshot: dict[str, Any] | None = None,
) -> GodInteractionDocument:
    interaction_type = classify_message(message)
    reply, next_action, potential_detected = build_reply(interaction_type, message, system_snapshot)
    resolved_memory_context = memory_context or []
    request_fingerprint = canonical_request_fingerprint(conversation_id, message, idempotency_key)
    fingerprint_payload = {
        "schema_version": "1.0",
        "policy_version": GOD_CONVERSATION_POLICY_VERSION,
        "conversation_id": conversation_id,
        "idempotency_key": idempotency_key,
        "request_fingerprint": request_fingerprint,
        "memory_context": resolved_memory_context,
        "system_snapshot": system_snapshot,
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
