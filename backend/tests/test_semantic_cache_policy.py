from __future__ import annotations

from app.cache.contracts import CacheIntent, CacheSensitivity
from app.cache.fingerprint import build_exact_key, normalize_query
from app.cache.policy import evaluate_policy
from app.inference.contracts import InferenceRequest, ModelRequirements


def request(query: str, **metadata) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "system", "content": "stable-system-v1"}, {"role": "user", "content": query}],
        model="model-a",
        requirements=ModelRequirements(preferred_provider="provider-a"),
        metadata={"creator_id": "creator-a", **metadata},
    )


def test_explanations_are_cacheable_private_by_default() -> None:
    evaluation = evaluate_policy(request("Explain how the Central Core works"), "Explain how the Central Core works")
    assert evaluation.eligible is True
    assert evaluation.intent is CacheIntent.EXPLANATION
    assert evaluation.sensitivity is CacheSensitivity.PRIVATE


def test_live_state_and_financial_live_queries_bypass() -> None:
    live = evaluate_policy(request("What is the system status now?"), "What is the system status now?")
    financial = evaluate_policy(request("What is the BTC price right now?"), "What is the BTC price right now?")
    assert live.eligible is False and live.intent is CacheIntent.LIVE_STATE
    assert financial.eligible is False and financial.intent is CacheIntent.FINANCIAL_LIVE


def test_action_capable_task_requests_always_bypass() -> None:
    evaluation = evaluate_policy(
        request("Explain this task", task_id="task-1", enable_capability_intents=True),
        "Explain this task",
    )
    assert evaluation.eligible is False
    assert evaluation.intent is CacheIntent.SYSTEM_COMMAND


def test_document_qa_requires_both_retrieval_and_knowledge_versions() -> None:
    incomplete = evaluate_policy(
        request("Explain the document", cache_intent="DOCUMENT_QA", knowledge_version="v2"),
        "Explain the document",
    )
    complete = evaluate_policy(
        request(
            "Explain the document",
            cache_intent="DOCUMENT_QA",
            knowledge_version="v2",
            retrieval_fingerprint="sha256:abc",
        ),
        "Explain the document",
    )
    assert incomplete.eligible is False
    assert complete.eligible is True
    assert complete.intent is CacheIntent.DOCUMENT_QA


def test_sensitive_and_no_cache_classifications_fail_closed() -> None:
    for sensitivity in ("SENSITIVE", "NO_CACHE", "invalid-value"):
        evaluation = evaluate_policy(
            request("Explain the architecture", cache_sensitivity=sensitivity),
            "Explain the architecture",
        )
        assert evaluation.eligible is False


def test_exact_identity_changes_across_creator_scope() -> None:
    normalized = normalize_query(" Explain   Central Core ")
    key_a = build_exact_key(normalized_query=normalized, context={"creator_scope": "creator-a"})
    key_b = build_exact_key(normalized_query=normalized, context={"creator_scope": "creator-b"})
    assert normalized == "explain central core"
    assert key_a != key_b
