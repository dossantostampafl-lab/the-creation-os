"""The Trinity: DEUS listens, SOPHIA understands, ROCKMAM shapes what is possible.

SOPHIA reads every Creator message for intent. When the Creator asks for something to be
brought into being, SOPHIA weighs its opportunities and risks and ROCKMAM turns it into an
objective and an executable plan. A deterministic guard has the final word on viability, so
the model can propose but never grant itself an unavailable Universe.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError

from app.cognition.contracts import (
    IntentClass,
    IntentEnvelope,
    MissionPlanCandidate,
    RockmamSynthesis,
    SophiaAssessment,
)
from app.inference.contracts import InferenceRequest, ModelRequirements
from app.inference.router import ModelRouter

TRINITY_VERSION = 1

ModelT = TypeVar("ModelT", bound=BaseModel)


class TrinityError(RuntimeError):
    """The model's reasoning could not be turned into a valid Trinity document."""


class RockmamVerdict(StrEnum):
    VIABLE = "VIABLE"
    REQUIRES_CREATOR = "REQUIRES_CREATOR"


class Verdict(BaseModel):
    result: RockmamVerdict
    reasons: list[str] = Field(default_factory=list)
    unavailable_universes: list[str] = Field(default_factory=list)


class _SophiaReply(BaseModel):
    opportunities: list[str] = Field(default_factory=list, max_length=5)
    risks: list[str] = Field(default_factory=list, max_length=5)
    recommendation: str = Field(..., min_length=1, max_length=4000)


class RockmamProposal(BaseModel):
    title: str = Field(..., min_length=3, max_length=256)
    synthesis: RockmamSynthesis
    mission_plan: MissionPlanCandidate


class TrinityDeliberation(BaseModel):
    title: str
    intent: IntentEnvelope
    sophia: SophiaAssessment
    rockmam: RockmamSynthesis
    mission_plan: MissionPlanCandidate
    verdict: Verdict

    def assessment_document(self, *, provider: str, model: str) -> dict[str, Any]:
        return {
            "version": TRINITY_VERSION,
            "provider": provider,
            "model": model,
            **self.model_dump(mode="json"),
        }


SOPHIA_PERCEPTION_PROMPT = (
    "You are SOPHIA, the understanding layer of THE CREATION OS. Classify the Creator's latest "
    "message. Reply with one JSON object and nothing else, shaped as "
    '{"intent_class": one of ["conversation", "information_request", "mission_candidate", '
    '"creator_decision", "system_command"], "summary": "<one sentence>", "confidence": <0..1>}. '
    "Use mission_candidate only when the Creator asks for something to be built, created, executed "
    "or achieved in the world, not for questions, opinions or small talk."
)

SOPHIA_ASSESSMENT_PROMPT = (
    "You are SOPHIA, the understanding layer of THE CREATION OS. The Creator wants something brought "
    "into being. Assess it. Reply with one JSON object and nothing else, shaped as "
    '{"opportunities": ["..."], "risks": ["..."], "recommendation": "<what should be done and why>"}. '
    "Be concrete and brief; at most five opportunities and five risks."
)

ROCKMAM_PROMPT = (
    "You are ROCKMAM, the possibility layer of THE CREATION OS. Turn the Creator's request and "
    "SOPHIA's assessment into a Mission proposal. Reply with one JSON object and nothing else, shaped as "
    '{"title": "<short Mission title>", '
    '"synthesis": {"objective": "...", "constraints": ["..."], "completion_criteria": ["..."]}, '
    '"mission_plan": {"strategy": "...", "steps": [{"step_key": "<lowercase-slug>", "title": "...", '
    '"description": "...", "universe": "<Universe code>", "position": 1, "depends_on": ["<step_key>"], '
    '"completion_criteria": {}}], "completion_criteria": {}}}. '
    "Use between one and eight steps, unique positions starting at 1, and no dependency cycles. "
    "Assign each step to one of the available Universes when one fits; otherwise name the Universe "
    "the step needs and the Creator will decide."
)


def parse_json_document(content: str, model: type[ModelT]) -> ModelT:
    """Validate the first JSON object in a model reply, tolerating Markdown fences and prose around it."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        raise TrinityError(f"{model.__name__}: reply contained no JSON object")
    try:
        return model.model_validate(json.loads(content[start:end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise TrinityError(f"{model.__name__}: {exc.__class__.__name__}") from exc


def judge(plan: MissionPlanCandidate, available_universes: set[str]) -> Verdict:
    """ROCKMAM's deterministic guard: a plan is viable only if every step has an active Universe."""
    unavailable = sorted({step.universe for step in plan.steps if step.universe not in available_universes})
    if not unavailable:
        return Verdict(result=RockmamVerdict.VIABLE)
    return Verdict(
        result=RockmamVerdict.REQUIRES_CREATOR,
        reasons=["The plan needs Universes that are not active yet."],
        unavailable_universes=unavailable,
    )


class TrinityEngine:
    def __init__(
        self,
        router: ModelRouter,
        *,
        provider: str,
        model: str,
        min_confidence: float,
    ) -> None:
        self.router = router
        self.provider = provider
        self.model = model
        self.min_confidence = min_confidence

    async def _ask(
        self,
        layer: str,
        system: str,
        user: str,
        schema: type[ModelT],
        *,
        max_output_tokens: int,
        creator_id: str,
    ) -> ModelT:
        response = await self.router.generate(InferenceRequest(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=self.model,
            requirements=ModelRequirements(
                preferred_provider=self.provider,
                max_output_tokens=max_output_tokens,
            ),
            metadata={
                "creator_id": creator_id,
                "route": f"trinity:{layer}",
                "cache_policy": "bypass",
                "cache_sensitivity": "PRIVATE",
                "tool_state_class": "read_only",
            },
        ))
        return parse_json_document(response.content, schema)

    async def perceive(self, message: str, recent: list[str], *, creator_id: str) -> IntentEnvelope:
        context = "\n".join(f"- {line}" for line in recent[-4:]) or "- (none)"
        return await self._ask(
            "sophia",
            SOPHIA_PERCEPTION_PROMPT,
            f"Recent Creator messages:\n{context}\n\nLatest message:\n{message}",
            IntentEnvelope,
            max_output_tokens=300,
            creator_id=creator_id,
        )

    def calls_for_deliberation(self, intent: IntentEnvelope) -> bool:
        return intent.intent_class == IntentClass.MISSION_CANDIDATE and intent.confidence >= self.min_confidence

    async def deliberate(
        self,
        message: str,
        intent: IntentEnvelope,
        available_universes: set[str],
        *,
        creator_id: str,
    ) -> TrinityDeliberation:
        sophia = await self._ask(
            "sophia",
            SOPHIA_ASSESSMENT_PROMPT,
            f"Creator request:\n{message}\n\nUnderstood as: {intent.summary}",
            _SophiaReply,
            max_output_tokens=800,
            creator_id=creator_id,
        )
        assessment = SophiaAssessment(intent=intent, **sophia.model_dump())
        universes = ", ".join(sorted(available_universes)) or "(none active)"
        proposal = await self._ask(
            "rockmam",
            ROCKMAM_PROMPT,
            (
                f"Creator request:\n{message}\n\n"
                f"SOPHIA's assessment:\n{json.dumps(sophia.model_dump(), ensure_ascii=False)}\n\n"
                f"Available Universes: {universes}"
            ),
            RockmamProposal,
            max_output_tokens=1500,
            creator_id=creator_id,
        )
        return TrinityDeliberation(
            title=proposal.title,
            intent=intent,
            sophia=assessment,
            rockmam=proposal.synthesis,
            mission_plan=proposal.mission_plan,
            verdict=judge(proposal.mission_plan, available_universes),
        )
