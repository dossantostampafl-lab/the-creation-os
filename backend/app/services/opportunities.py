from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from app.config import settings
from app.core.domain import Actor, DomainError, InceptionStatus, require_creator
from app.models.entities import Conversation, Inception, Message
from app.models.opportunity import Opportunity, OpportunityObservation
from app.repositories.capabilities import CapabilityRepository
from app.repositories.opportunities import OpportunityRepository
from app.services.capability_governance import CapabilityGovernanceService


class OpportunityStatus(StrEnum):
    DETECTED = "detected"
    UNDER_ANALYSIS = "under_analysis"
    PENDING_CREATOR_REVIEW = "pending_creator_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONVERTED_TO_INCEPTION = "converted_to_inception"


class OpportunityError(DomainError):
    pass


class OPPORTUNITY_NOT_FOUND(OpportunityError):
    pass


class OPPORTUNITY_INVALID_TRANSITION(OpportunityError):
    pass


class OPPORTUNITY_ALREADY_REVIEWED(OpportunityError):
    pass


class OPPORTUNITY_EXPIRED(OpportunityError):
    pass


class OPPORTUNITY_EVIDENCE_REQUIRED(OpportunityError):
    pass


class OPPORTUNITY_PERMISSION_DENIED(OpportunityError):
    pass


class OPPORTUNITY_NOT_APPROVED(OpportunityError):
    pass


class OPPORTUNITY_INCEPTION_ALREADY_CREATED(OpportunityError):
    pass


class OBSERVATION_INVALID(OpportunityError):
    pass


class OBSERVATION_DUPLICATE(OpportunityError):
    pass


@dataclass(frozen=True)
class ScoreResult:
    confidence: float
    impact: float
    urgency: float
    risk: float
    source_reliability: float
    priority_score: float
    scoring: dict[str, Any]


def clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


class OpportunityDiscoveryService:
    def __init__(
        self,
        repository: OpportunityRepository,
        governance: CapabilityGovernanceService | None = None,
    ) -> None:
        self.repository = repository
        self.governance = governance

    async def ingest_observation(self, actor: Actor, payload: dict[str, Any], correlation_id: str) -> OpportunityObservation:
        require_creator(actor, "ingest opportunity observation")
        data = self._normalize_observation(payload)
        fingerprint = self._observation_fingerprint(data)
        if await self.repository.observation_by_fingerprint(fingerprint):
            await self.repository.add_event(
                "observation.rejected",
                None,
                actor.id,
                actor.role,
                correlation_id,
                {"reason": "duplicate", "fingerprint": fingerprint},
            )
            await self.repository.commit()
            raise OBSERVATION_DUPLICATE("Observation already exists")
        item = await self.repository.add_observation(OpportunityObservation(**data, observation_fingerprint=fingerprint))
        await self.repository.add_event(
            "observation.ingested",
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"observation_id": item.id, "universe": item.universe, "source": item.source, "correlation_key": item.correlation_key},
        )
        await self.repository.commit()
        return item

    async def run_discovery(self, actor: Actor, observations: list[dict[str, Any]], correlation_id: str) -> list[Opportunity]:
        require_creator(actor, "run opportunity discovery")
        await self._governance().authorize_execution(
            actor,
            connector_id="opportunity",
            connector_capability="run_discovery",
            correlation_id=correlation_id,
        )
        ingested: list[OpportunityObservation] = []
        for payload in observations:
            try:
                ingested.append(await self._ingest_without_commit(actor, payload, correlation_id))
            except OBSERVATION_DUPLICATE:
                existing = await self.repository.observation_by_fingerprint(self._observation_fingerprint(self._normalize_observation(payload)))
                if existing is not None:
                    ingested.append(existing)
        await self.repository.commit()
        opportunities = await self.detect(actor, correlation_id)
        return opportunities

    async def detect(self, actor: Actor, correlation_id: str) -> list[Opportunity]:
        require_creator(actor, "detect opportunities")
        enabled_universes = {item.strip() for item in settings.opportunity_enabled_universes.split(",") if item.strip()}
        observations = await self.repository.observations_for_discovery(enabled_universes)
        grouped: dict[str, list[OpportunityObservation]] = {}
        for observation in observations:
            grouped.setdefault(observation.correlation_key, []).append(observation)
        detected: list[Opportunity] = []
        for correlation_key, items in grouped.items():
            if len(items) < settings.opportunity_min_evidence:
                continue
            score = self._score(items)
            if score.priority_score < settings.opportunity_min_score:
                continue
            opportunity = await self._create_or_update_opportunity(actor, correlation_id, correlation_key, items, score)
            detected.append(opportunity)
        await self.repository.commit()
        return sorted(detected, key=lambda item: item.priority_score, reverse=True)

    async def list_opportunities(self, actor: Actor, universe: str | None, status: str | None, min_priority: float | None, limit: int, offset: int) -> list[Opportunity]:
        require_creator(actor, "list opportunities")
        return await self.repository.opportunities(universe=universe, status=status, min_priority=min_priority, limit=limit, offset=offset)

    async def get_opportunity(self, actor: Actor, opportunity_id: str) -> Opportunity:
        require_creator(actor, "view opportunity")
        item = await self.repository.opportunity(opportunity_id)
        if item is None:
            raise OPPORTUNITY_NOT_FOUND("Opportunity not found")
        return item

    async def ranking(self, actor: Actor, universe: str | None, limit: int) -> list[Opportunity]:
        require_creator(actor, "rank opportunities")
        return await self.repository.opportunities(universe=universe, status=None, min_priority=None, limit=limit, offset=0)

    async def expire(self, actor: Actor, correlation_id: str) -> list[Opportunity]:
        require_creator(actor, "expire opportunities")
        now = datetime.now(timezone.utc)
        expired = []
        for item in await self.repository.expirable(now):
            previous = item.status
            item.status = OpportunityStatus.EXPIRED.value
            expired.append(item)
            await self.repository.add_event(
                "opportunity.expired",
                item.id,
                actor.id,
                actor.role,
                correlation_id,
                {"previous_status": previous, "new_status": item.status, "reason": "expires_at elapsed"},
            )
        await self.repository.commit()
        return expired

    async def approve(self, actor: Actor, opportunity_id: str, reason: str | None, correlation_id: str) -> Opportunity:
        return await self._review(actor, opportunity_id, OpportunityStatus.APPROVED, reason, correlation_id)

    async def reject(self, actor: Actor, opportunity_id: str, reason: str | None, correlation_id: str) -> Opportunity:
        return await self._review(actor, opportunity_id, OpportunityStatus.REJECTED, reason, correlation_id)

    async def convert_to_inception(self, actor: Actor, opportunity_id: str, correlation_id: str) -> Opportunity:
        require_creator(actor, "convert opportunity to Inception")
        item = await self.repository.opportunity(opportunity_id, lock=True)
        if item is None:
            raise OPPORTUNITY_NOT_FOUND("Opportunity not found")
        if item.inception_id is not None:
            await self._denied(actor, item, correlation_id, "OPPORTUNITY_INCEPTION_ALREADY_CREATED")
            raise OPPORTUNITY_INCEPTION_ALREADY_CREATED("Opportunity already created an Inception")
        if item.status != OpportunityStatus.APPROVED.value:
            await self._denied(actor, item, correlation_id, "OPPORTUNITY_NOT_APPROVED")
            raise OPPORTUNITY_NOT_APPROVED("Opportunity must be approved before conversion")
        conversation = await self.repository.add_conversation(Conversation(creator_id=actor.id, title="Opportunity Discovery", status="active"))
        message = await self.repository.add_message(
            Message(
                conversation_id=conversation.id,
                role="god",
                actor_id=actor.id,
                correlation_id=correlation_id,
                content=f"Opportunity approved for Inception: {item.title}",
                route="opportunity",
                metadata_json={"opportunity_id": item.id},
            )
        )
        inception = await self.repository.add_inception(
            Inception(
                conversation_id=conversation.id,
                source_message_id=message.id,
                title=item.title,
                description=item.summary,
                status=InceptionStatus.PROPOSED.value,
                trinity_assessment_json={"source": "opportunity_discovery", "opportunity_id": item.id},
            )
        )
        previous = item.status
        item.status = OpportunityStatus.CONVERTED_TO_INCEPTION.value
        item.inception_id = inception.id
        await self.repository.add_event(
            "opportunity.converted_to_inception",
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"previous_status": previous, "new_status": item.status, "inception_id": inception.id},
        )
        await self.repository.commit()
        return item

    async def _review(self, actor: Actor, opportunity_id: str, target: OpportunityStatus, reason: str | None, correlation_id: str) -> Opportunity:
        require_creator(actor, f"{target.value} opportunity")
        item = await self.repository.opportunity(opportunity_id, lock=True)
        if item is None:
            raise OPPORTUNITY_NOT_FOUND("Opportunity not found")
        if item.expires_at <= datetime.now(timezone.utc):
            await self._denied(actor, item, correlation_id, "OPPORTUNITY_EXPIRED")
            raise OPPORTUNITY_EXPIRED("Opportunity is expired")
        if item.status != OpportunityStatus.PENDING_CREATOR_REVIEW.value:
            await self._denied(actor, item, correlation_id, "OPPORTUNITY_INVALID_TRANSITION")
            raise OPPORTUNITY_INVALID_TRANSITION("Opportunity is not pending Creator review")
        previous = item.status
        item.status = target.value
        item.reviewed_at = datetime.now(timezone.utc)
        item.reviewed_by = actor.id
        if target is OpportunityStatus.REJECTED:
            item.rejection_reason = reason
        await self.repository.add_event(
            f"opportunity.{target.value}",
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"previous_status": previous, "new_status": item.status, "reason": reason},
        )
        await self.repository.commit()
        return item

    async def _ingest_without_commit(self, actor: Actor, payload: dict[str, Any], correlation_id: str) -> OpportunityObservation:
        data = self._normalize_observation(payload)
        fingerprint = self._observation_fingerprint(data)
        existing = await self.repository.observation_by_fingerprint(fingerprint)
        if existing is not None:
            raise OBSERVATION_DUPLICATE("Observation already exists")
        item = await self.repository.add_observation(OpportunityObservation(**data, observation_fingerprint=fingerprint))
        await self.repository.add_event("observation.ingested", item.id, actor.id, actor.role, correlation_id, {"observation_id": item.id})
        return item

    async def _create_or_update_opportunity(
        self,
        actor: Actor,
        correlation_id: str,
        correlation_key: str,
        observations: list[OpportunityObservation],
        score: ScoreResult,
    ) -> Opportunity:
        first = observations[0]
        evidence = self._evidence_payload(observations)
        risks = {"items": ["Informational only; no financial operation is authorized.", "Signals may be stale or incomplete."]}
        existing = await self.repository.opportunity_by_correlation(correlation_key)
        now = datetime.now(timezone.utc)
        if existing is None:
            item = await self.repository.add_opportunity(
                Opportunity(
                    title=f"{first.subject}: opportunity signal",
                    universe=first.universe,
                    category=self._category(first),
                    status=OpportunityStatus.PENDING_CREATOR_REVIEW.value,
                    summary=self._summary(first, observations),
                    explanation=self._explanation(observations, score),
                    confidence=score.confidence,
                    impact=score.impact,
                    urgency=score.urgency,
                    risk=score.risk,
                    source_reliability=score.source_reliability,
                    priority_score=score.priority_score,
                    recommended_action="Iniciar investigacao aprofundada. Nenhuma operacao financeira deve ser executada.",
                    evidence=evidence,
                    risks=risks,
                    scoring=score.scoring,
                    correlation_key=correlation_key,
                    detected_at=now,
                    expires_at=now + timedelta(hours=settings.opportunity_expiration_hours),
                )
            )
            event_type = "opportunity.detected"
        else:
            item = existing
            item.summary = self._summary(first, observations)
            item.explanation = self._explanation(observations, score)
            item.confidence = score.confidence
            item.impact = score.impact
            item.urgency = score.urgency
            item.risk = score.risk
            item.source_reliability = score.source_reliability
            item.priority_score = score.priority_score
            item.evidence = evidence
            item.risks = risks
            item.scoring = score.scoring
            event_type = "opportunity.updated"
        for observation in observations:
            await self.repository.add_evidence(item.id, observation.id)
        await self.repository.add_event(
            event_type,
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"status": item.status, "score": item.priority_score, "evidence_count": len(observations), "correlation_key": correlation_key},
        )
        await self.repository.add_event(
            "opportunity.review.requested",
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"status": item.status, "reason": "score above threshold"},
        )
        return item

    def _normalize_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = ["universe", "source", "subject", "event_type", "title", "summary"]
        if any(not str(payload.get(key, "")).strip() for key in required):
            raise OBSERVATION_INVALID("Observation required fields are missing")
        universe = str(payload["universe"]).strip().lower()
        enabled = {item.strip() for item in settings.opportunity_enabled_universes.split(",") if item.strip()}
        if universe not in enabled:
            raise OBSERVATION_INVALID("Observation universe is not enabled")
        source_reliability = clamp(float(payload.get("source_reliability", 0)))
        if source_reliability < settings.opportunity_min_source_reliability:
            raise OBSERVATION_INVALID("Observation source reliability is below threshold")
        observed_at = payload.get("observed_at") or datetime.now(timezone.utc)
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        correlation_key = str(payload.get("correlation_key") or f"{universe}:{payload['subject']}:{payload['event_type']}").strip().lower()
        return {
            "universe": universe,
            "source": str(payload["source"]).strip(),
            "subject": str(payload["subject"]).strip(),
            "event_type": str(payload["event_type"]).strip().lower(),
            "title": str(payload["title"]).strip(),
            "summary": str(payload["summary"]).strip(),
            "observed_at": observed_at,
            "normalized_data": payload.get("normalized_data") or payload.get("raw_data") or {},
            "evidence": payload.get("evidence") or {},
            "source_reliability": source_reliability,
            "correlation_key": correlation_key,
        }

    def _observation_fingerprint(self, data: dict[str, Any]) -> str:
        material = {
            "universe": data["universe"],
            "source": data["source"],
            "subject": data["subject"],
            "event_type": data["event_type"],
            "correlation_key": data["correlation_key"],
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _score(self, observations: list[OpportunityObservation]) -> ScoreResult:
        reliability = clamp(sum(item.source_reliability for item in observations) / len(observations))
        confidence = clamp(0.45 + 0.12 * len(observations) + reliability * 0.25)
        impact = clamp(0.55 + 0.1 * sum(1 for item in observations if item.event_type in {"volume_anomaly", "launch", "macro_event"}))
        urgency = clamp(0.5 + 0.1 * sum(1 for item in observations if item.event_type in {"volatility_increase", "regulatory_change"}))
        risk = clamp(0.25 + 0.08 * sum(1 for item in observations if item.event_type in {"divergence", "rumor"}))
        weights = {"confidence": 0.35, "impact": 0.30, "urgency": 0.20, "source_reliability": 0.15}
        risk_penalty = round(risk * 0.20, 4)
        raw_score = confidence * weights["confidence"] + impact * weights["impact"] + urgency * weights["urgency"] + reliability * weights["source_reliability"] - risk_penalty
        final = clamp(raw_score)
        return ScoreResult(
            confidence,
            impact,
            urgency,
            risk,
            reliability,
            final,
            {"weights": weights, "risk_penalty": risk_penalty, "raw_score": round(raw_score, 4), "final_score": final},
        )

    def _category(self, observation: OpportunityObservation) -> str:
        if observation.universe == "finance":
            return "informational_financial_investigation"
        return "technology_business_signal"

    def _summary(self, first: OpportunityObservation, observations: list[OpportunityObservation]) -> str:
        return f"{len(observations)} signal(s) correlated for {first.subject}: {first.summary}"

    def _explanation(self, observations: list[OpportunityObservation], score: ScoreResult) -> str:
        events = ", ".join(sorted({item.event_type for item in observations}))
        return (
            f"Deterministic correlation found events [{events}] with average reliability {score.source_reliability}. "
            f"Priority score {score.priority_score} is based on confidence, impact, urgency, reliability and risk penalty."
        )

    def _evidence_payload(self, observations: list[OpportunityObservation]) -> dict[str, Any]:
        return {
            "observations": [
                {
                    "id": item.id,
                    "source": item.source,
                    "event_type": item.event_type,
                    "observed_at": item.observed_at.isoformat(),
                    "source_reliability": item.source_reliability,
                    "summary": item.summary,
                }
                for item in observations
            ]
        }

    async def _denied(self, actor: Actor, item: Opportunity, correlation_id: str, code: str) -> None:
        await self.repository.add_event(
            "opportunity.execution.denied",
            item.id,
            actor.id,
            actor.role,
            correlation_id,
            {"status": item.status, "code": code},
        )
        await self.repository.commit()

    def _governance(self) -> CapabilityGovernanceService:
        if self.governance is not None:
            return self.governance
        return CapabilityGovernanceService(CapabilityRepository(self.repository.session))
