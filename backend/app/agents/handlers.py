import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.domain import DomainError


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
        )
    ]
)
