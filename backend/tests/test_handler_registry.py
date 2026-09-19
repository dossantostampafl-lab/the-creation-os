from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from app.agents.handlers import (
    ExecutionContext,
    HandlerDefinition,
    HandlerError,
    HandlerRegistry,
    ObjectPayload,
    StructuredResult,
    default_registry,
)


def context():
    return ExecutionContext("e", "m", "t", "a", "c", datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_default_handler_is_deterministic_and_validates_result():
    handler = default_registry.resolve("structured_echo", "1.0", "planning")
    result = await default_registry.invoke(handler, context(), {"value": 3})
    assert result.status == "succeeded" and result.output == {"value": 3} and result.metrics == {"fields": 1}


def test_registry_rejects_unknown_mismatch_duplicate_and_forbidden_policy():
    registry = HandlerRegistry()

    async def valid(_, payload):
        return {"status": "succeeded", "output": payload, "metrics": {}, "warnings": [], "error": None}

    handler = HandlerDefinition("safe", "1", "planning", ObjectPayload, StructuredResult, 1, True, "none", valid)
    registry.register(handler)
    with pytest.raises(HandlerError, match="already"):
        registry.register(handler)
    with pytest.raises(HandlerError, match="not registered"):
        registry.resolve("missing", "1", "planning")
    with pytest.raises(HandlerError, match="mismatch"):
        registry.resolve("safe", "1", "other")
    for deterministic, policy, timeout in ((False, "none", 1), (True, "filesystem", 1), (True, "none", 0)):
        with pytest.raises(HandlerError, match="policy"):
            HandlerRegistry([HandlerDefinition("bad", str(timeout), "planning", ObjectPayload, StructuredResult, timeout, deterministic, policy, valid)])


@pytest.mark.asyncio
async def test_registry_rejects_invalid_input_and_output():
    class RequiredInput(BaseModel):
        value: int

    async def bad_output(_, payload):
        return {"unexpected": payload}

    registry = HandlerRegistry(
        [HandlerDefinition("bad", "1", "planning", RequiredInput, StructuredResult, 1, True, "none", bad_output)]
    )
    handler = registry.resolve("bad", "1", "planning")
    with pytest.raises(HandlerError, match="schema"):
        await registry.invoke(handler, context(), {})
    with pytest.raises(HandlerError, match="schema"):
        await registry.invoke(handler, context(), {"value": 1})


@pytest.mark.asyncio
async def test_knowledge_research_handler_produces_deterministic_typed_output():
    handler = default_registry.resolve("knowledge_research", "1.0", "knowledge_research")
    payload = {"topic": "Trinity orchestration", "notes": ["b note", "a note", "a note", "  "]}
    first = await default_registry.invoke(handler, context(), payload)
    second = await default_registry.invoke(handler, context(), payload)
    assert first.model_dump() == second.model_dump()
    assert first.status == "succeeded"
    assert first.output["key_points"] == ["a note", "b note"]
    assert first.output["sources"] == ["internal-memory:mission:m", "internal-memory:task:t"]
    assert "Trinity orchestration" in first.output["summary"]


@pytest.mark.asyncio
async def test_engineering_design_handler_decomposes_requirements_deterministically():
    handler = default_registry.resolve("engineering_design", "1.0", "engineering_design")
    payload = {
        "requirements": ["Support pgvector", "Support pgvector", " "],
        "known_dependencies": ["redis", "redis", "postgres"],
    }
    result = await default_registry.invoke(handler, context(), payload)
    assert result.status == "succeeded"
    assert result.output["components"] == ["component-1: Support pgvector", "component-2: Support pgvector"]
    assert result.output["dependencies"] == ["postgres", "redis"]
    assert len(result.output["acceptance_criteria"]) == 2


@pytest.mark.asyncio
async def test_security_review_handler_flags_sensitive_keys_and_is_compliant_otherwise():
    handler = default_registry.resolve("security_review", "1.0", "security_review")
    flagged = await default_registry.invoke(
        handler, context(), {"subject": "worker credential", "payload_keys": ["api_key", "username"]}
    )
    assert flagged.output["compliant"] is False
    assert flagged.output["risk_level"] == "high"
    assert flagged.output["findings"][0] == "Sensitive key exposed: api_key"

    clean = await default_registry.invoke(
        handler, context(), {"subject": "public config", "payload_keys": ["username", "locale"]}
    )
    assert clean.output["compliant"] is True
    assert clean.output["risk_level"] == "low"


def test_resolve_by_capability_finds_each_registered_handler_and_rejects_unknown():
    for capability, name in (
        ("planning", "structured_echo"),
        ("knowledge_research", "knowledge_research"),
        ("engineering_design", "engineering_design"),
        ("security_review", "security_review"),
    ):
        assert default_registry.resolve_by_capability(capability).name == name
    with pytest.raises(HandlerError, match="No handler registered"):
        default_registry.resolve_by_capability("unknown_capability")
