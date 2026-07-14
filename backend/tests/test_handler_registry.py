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
