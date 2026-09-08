from __future__ import annotations

from app.cognition.contracts import (
    InceptionCandidate,
    IntentClass,
    IntentEnvelope,
    MissionPlanCandidate,
    MissionStepCandidate,
    RockmamSynthesis,
    SophiaAssessment,
    TrinityAssessment,
)


def test_trinity_assessment_roundtrip() -> None:
    intent = IntentEnvelope(
        intent_class=IntentClass.MISSION_CANDIDATE,
        summary="Build the Creation Kernel",
        confidence=0.95,
    )
    sophia = SophiaAssessment(
        intent=intent,
        opportunities=["Close Gate A"],
        risks=["Unauthorized external effects"],
        recommendation="Proceed through Creator authorization",
    )
    rockmam = RockmamSynthesis(
        objective="Implement the authorized Creation Kernel",
        constraints=["DEUS does not execute operational work"],
        completion_criteria=["Authorized mission reaches a terminal state through runtime"],
    )
    trinity = TrinityAssessment(sophia=sophia, rockmam=rockmam)

    restored = TrinityAssessment.model_validate(trinity.model_dump())

    assert restored.sophia.intent.intent_class is IntentClass.MISSION_CANDIDATE
    assert restored.rockmam.objective == rockmam.objective


def test_inception_candidate_contains_trinity_and_dependency_plan() -> None:
    trinity = TrinityAssessment(
        sophia=SophiaAssessment(
            intent=IntentEnvelope(
                intent_class=IntentClass.MISSION_CANDIDATE,
                summary="Implement Gate A",
                confidence=1.0,
            ),
            recommendation="Create an Inception for Creator review",
        ),
        rockmam=RockmamSynthesis(
            objective="Close Gate A",
            completion_criteria=["Kernel lifecycle is executable"],
        ),
    )
    plan = MissionPlanCandidate(
        strategy="Build deterministic kernel stages",
        steps=[
            MissionStepCandidate(
                step_key="contracts",
                title="Create contracts",
                description="Define structured cognition contracts",
                universe="engineering",
                position=1,
            ),
            MissionStepCandidate(
                step_key="runtime",
                title="Create runtime",
                description="Execute only after authorization",
                universe="engineering",
                position=2,
                depends_on=["contracts"],
            ),
        ],
        completion_criteria={"gate_a": True},
    )
    candidate = InceptionCandidate(
        title="Creation Kernel Gate A",
        description="Implement the minimum safe operational kernel",
        trinity_assessment=trinity,
        mission_plan=plan,
    )

    assert candidate.mission_plan.steps[1].depends_on == ["contracts"]
    assert candidate.trinity_assessment.sophia.intent.summary == "Implement Gate A"
