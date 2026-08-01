import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.domain import DomainError
from app.repositories.domain import SENSITIVE_KEYS


class HandlerError(DomainError):
    pass


class ObjectPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class StructuredResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(succeeded|failed)$")
    output: dict
    metrics: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    mission_id: str
    task_id: str
    agent_id: str
    capability_id: str
    deadline: datetime


HandlerCallable = Callable[[ExecutionContext, dict], Awaitable[dict]]


@dataclass(frozen=True)
class HandlerDefinition:
    name: str
    version: str
    capability: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    timeout_seconds: int
    deterministic: bool
    side_effect_policy: str
    function: HandlerCallable


class HandlerRegistry:
    def __init__(self, handlers=()):
        self._handlers: dict[tuple[str, str], HandlerDefinition] = {}
        for handler in handlers:
            self.register(handler)

    def register(self, handler: HandlerDefinition) -> None:
        if not handler.deterministic or handler.side_effect_policy != "none" or handler.timeout_seconds < 1:
            raise HandlerError("Handler policy is not permitted")
        key = (handler.name, handler.version)
        if key in self._handlers:
            raise HandlerError("Handler already registered")
        self._handlers[key] = handler

    def resolve(self, name: str, version: str, capability: str) -> HandlerDefinition:
        handler = self._handlers.get((name, version))
        if handler is None:
            raise HandlerError("Handler is not registered")
        if handler.capability != capability:
            raise HandlerError("Handler capability mismatch")
        return handler

    def resolve_by_capability(self, capability: str) -> HandlerDefinition:
        for handler in self._handlers.values():
            if handler.capability == capability:
                return handler
        raise HandlerError(f"No handler registered for capability: {capability}")

    async def invoke(self, handler: HandlerDefinition, context: ExecutionContext, payload: dict) -> StructuredResult:
        try:
            validated_input = handler.input_schema.model_validate(payload).model_dump()
            raw = await handler.function(context, validated_input)
            validated_output = handler.output_schema.model_validate(raw)
            return StructuredResult.model_validate(validated_output.model_dump())
        except ValidationError as exc:
            raise HandlerError("Handler schema validation failed") from exc


async def structured_echo(context: ExecutionContext, payload: dict) -> dict:
    await asyncio.sleep(0)
    return {"status": "succeeded", "output": payload, "metrics": {"fields": len(payload)}, "warnings": [], "error": None}


class KnowledgeResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(..., min_length=1, max_length=500)
    notes: list[str] = Field(default_factory=list)


class KnowledgeResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    key_points: list[str]
    sources: list[str]


class KnowledgeResearchResult(StructuredResult):
    output: KnowledgeResearchOutput


async def knowledge_research(context: ExecutionContext, payload: dict) -> dict:
    """Organizes the given notes into a structured synthesis. Does not query any
    external memory store — ExecutionContext carries no database session (v0.4.5
    contract), so "internal sources" are cited as identifiers, not fetched."""
    topic = payload["topic"]
    notes = payload["notes"]
    key_points = sorted({note.strip() for note in notes if note.strip()})
    summary = f"Knowledge synthesis for '{topic}': {len(key_points)} organized point(s) from internal notes."
    sources = [f"internal-memory:mission:{context.mission_id}", f"internal-memory:task:{context.task_id}"]
    return {
        "status": "succeeded",
        "output": {"summary": summary, "key_points": key_points, "sources": sources},
        "metrics": {"note_count": len(notes), "key_point_count": len(key_points)},
        "warnings": [],
        "error": None,
    }


class EngineeringDesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[str] = Field(..., min_length=1)
    known_dependencies: list[str] = Field(default_factory=list)


class EngineeringDesignOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: str
    components: list[str]
    dependencies: list[str]
    acceptance_criteria: list[str]


class EngineeringDesignResult(StructuredResult):
    output: EngineeringDesignOutput


async def engineering_design(context: ExecutionContext, payload: dict) -> dict:
    """Transforms requirements into a technical proposal. Never executes code —
    only decomposes and organizes the given requirements/dependencies."""
    requirements = [item.strip() for item in payload["requirements"] if item.strip()]
    components = [f"component-{index + 1}: {requirement}" for index, requirement in enumerate(requirements)]
    dependencies = sorted({item.strip() for item in payload["known_dependencies"] if item.strip()})
    acceptance_criteria = [f"Requirement satisfied: {requirement}" for requirement in requirements]
    proposal = f"Technical proposal covering {len(requirements)} requirement(s), decomposed into {len(components)} component(s)."
    return {
        "status": "succeeded",
        "output": {
            "proposal": proposal,
            "components": components,
            "dependencies": dependencies,
            "acceptance_criteria": acceptance_criteria,
        },
        "metrics": {"requirement_count": len(requirements), "dependency_count": len(dependencies)},
        "warnings": [],
        "error": None,
    }


class SecurityReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(..., min_length=1, max_length=500)
    payload_keys: list[str] = Field(default_factory=list)


class SecurityReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_level: str
    findings: list[str]
    compliant: bool


class SecurityReviewResult(StructuredResult):
    output: SecurityReviewOutput


async def security_review(context: ExecutionContext, payload: dict) -> dict:
    """Reviews risk/permission/secret-exposure by checking payload_keys against the
    same SENSITIVE_KEYS set already used to sanitize Chronicle payloads
    (app/repositories/domain.py) — reused, not reinvented."""
    subject = payload["subject"]
    keys = payload["payload_keys"]
    exposed = sorted({key for key in keys if key.strip().lower().replace("-", "_") in SENSITIVE_KEYS})
    compliant = not exposed
    risk_level = "high" if exposed else "low"
    findings = [f"Sensitive key exposed: {key}" for key in exposed]
    findings.append(
        f"Review subject '{subject}' fails secret-exposure compliance."
        if exposed
        else f"Review subject '{subject}' has no detected secret exposure."
    )
    return {
        "status": "succeeded",
        "output": {"risk_level": risk_level, "findings": findings, "compliant": compliant},
        "metrics": {"checked_key_count": len(keys), "exposed_key_count": len(exposed)},
        "warnings": [],
        "error": None,
    }


default_registry = HandlerRegistry(
    [
        HandlerDefinition(
            name="structured_echo",
            version="1.0",
            capability="planning",
            input_schema=ObjectPayload,
            output_schema=StructuredResult,
            timeout_seconds=5,
            deterministic=True,
            side_effect_policy="none",
            function=structured_echo,
        ),
        HandlerDefinition(
            name="knowledge_research",
            version="1.0",
            capability="knowledge_research",
            input_schema=KnowledgeResearchInput,
            output_schema=KnowledgeResearchResult,
            timeout_seconds=5,
            deterministic=True,
            side_effect_policy="none",
            function=knowledge_research,
        ),
        HandlerDefinition(
            name="engineering_design",
            version="1.0",
            capability="engineering_design",
            input_schema=EngineeringDesignInput,
            output_schema=EngineeringDesignResult,
            timeout_seconds=5,
            deterministic=True,
            side_effect_policy="none",
            function=engineering_design,
        ),
        HandlerDefinition(
            name="security_review",
            version="1.0",
            capability="security_review",
            input_schema=SecurityReviewInput,
            output_schema=SecurityReviewResult,
            timeout_seconds=5,
            deterministic=True,
            side_effect_policy="none",
            function=security_review,
        ),
    ]
)
