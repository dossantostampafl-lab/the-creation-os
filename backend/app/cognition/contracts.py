from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class IntentClass(str, Enum):
    CONVERSATION = "conversation"
    INFORMATION_REQUEST = "information_request"
    MISSION_CANDIDATE = "mission_candidate"
    CREATOR_DECISION = "creator_decision"
    SYSTEM_COMMAND = "system_command"


class IntentEnvelope(BaseModel):
    intent_class: IntentClass
    summary: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(..., ge=0.0, le=1.0)
    context: dict[str, Any] = Field(default_factory=dict)


class SophiaAssessment(BaseModel):
    intent: IntentEnvelope
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendation: str = Field(..., min_length=1, max_length=4000)


class RockmamSynthesis(BaseModel):
    objective: str = Field(..., min_length=1, max_length=4000)
    constraints: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)


class TrinityAssessment(BaseModel):
    sophia: SophiaAssessment
    rockmam: RockmamSynthesis


class MissionStepCandidate(BaseModel):
    step_key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=8000)
    universe: str = Field(..., min_length=1, max_length=64)
    position: int = Field(..., ge=1)
    depends_on: list[str] = Field(default_factory=list)
    completion_criteria: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def cannot_depend_on_self(self) -> "MissionStepCandidate":
        if self.step_key in self.depends_on:
            raise ValueError("mission step cannot depend on itself")
        return self


class MissionPlanCandidate(BaseModel):
    strategy: str = Field(..., min_length=1, max_length=8000)
    steps: list[MissionStepCandidate] = Field(..., min_length=1)
    completion_criteria: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dag_references(self) -> "MissionPlanCandidate":
        keys = [step.step_key for step in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("mission step keys must be unique")
        positions = [step.position for step in self.steps]
        if len(positions) != len(set(positions)):
            raise ValueError("mission step positions must be unique")
        known = set(keys)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"unknown mission step dependencies: {sorted(missing)}")
        visiting: set[str] = set()
        visited: set[str] = set()
        dependencies = {step.step_key: set(step.depends_on) for step in self.steps}

        def visit(key: str) -> None:
            if key in visiting:
                raise ValueError("mission plan dependency cycle detected")
            if key in visited:
                return
            visiting.add(key)
            for dependency in dependencies[key]:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in keys:
            visit(key)
        return self


class InceptionCandidate(BaseModel):
    title: str = Field(..., min_length=3, max_length=256)
    description: str = Field(..., min_length=1, max_length=8000)
    trinity_assessment: TrinityAssessment
    mission_plan: MissionPlanCandidate
