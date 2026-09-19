"""Regression guard for the frozen v0.4.5 Handler Registry contract, the same
spirit as frontend/src/components/LivingDashboard.frozenSpec.test.ts: a
literal, cheap check that catches someone reintroducing exactly the
regression this project has already avoided once (Lote 2.5 investigated, and
rejected, adding a database session to ExecutionContext to solve the
KnowledgeResearchAgent memory gap — see ARCHITECTURE.md's Lote 2.5 entry).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from app.agents.handlers import ExecutionContext, HandlerRegistry

FORBIDDEN_FIELD_NAME_FRAGMENTS = ("session", "connection", "conn", "engine", "repository", "repo", "credential", "token", "db")


def test_execution_context_is_frozen():
    assert dataclasses.is_dataclass(ExecutionContext)
    assert ExecutionContext.__dataclass_fields__  # has fields at all
    assert ExecutionContext.__dataclass_params__.frozen is True


def test_execution_context_carries_no_database_or_io_handle():
    """The exact fixture of the frozen contract: only plain identifiers/a
    deadline, never a session, connection, repository, or credential — that is
    what makes handler functions safely deterministic and side-effect-free."""
    field_names = [f.name for f in dataclasses.fields(ExecutionContext)]
    for name in field_names:
        lowered = name.lower()
        for fragment in FORBIDDEN_FIELD_NAME_FRAGMENTS:
            assert fragment not in lowered, f"ExecutionContext.{name} looks like it carries I/O/state ({fragment!r})"

    context = ExecutionContext("e", "m", "t", "a", "c", datetime.now(timezone.utc))
    for field_value in dataclasses.astuple(context):
        assert isinstance(field_value, (str, datetime)), (
            f"ExecutionContext field value {field_value!r} is not a plain str/datetime — "
            "only identifiers and a deadline are permitted"
        )


def test_handler_registry_still_rejects_non_deterministic_or_side_effecting_handlers():
    """Same guardrail HandlerRegistry.register() already enforces at runtime —
    pinned here so it can never be silently loosened."""
    from app.agents.handlers import HandlerDefinition, HandlerError, ObjectPayload, StructuredResult

    async def handler(_, payload):
        return {"status": "succeeded", "output": payload, "metrics": {}, "warnings": [], "error": None}

    for deterministic, side_effect_policy, timeout_seconds in (
        (False, "none", 1),
        (True, "network", 1),
        (True, "none", 0),
    ):
        registry = HandlerRegistry()
        definition = HandlerDefinition(
            "x", "1", "planning", ObjectPayload, StructuredResult, timeout_seconds, deterministic, side_effect_policy, handler
        )
        try:
            registry.register(definition)
            raised = False
        except HandlerError:
            raised = True
        assert raised, (deterministic, side_effect_policy, timeout_seconds)
