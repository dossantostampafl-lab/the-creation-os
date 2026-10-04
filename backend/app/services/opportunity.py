from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.domain import InvalidOrigin, MissionStatus
from app.models.entities import Mission, Universe, UniverseMemory
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.repositories.domain import DomainRepository
from app.schemas.opportunity import OpportunityThesisCreate
from app.services.domain import NotFoundError


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def normalize_opportunity_fingerprint(
    *,
    sector: str,
    problem_or_gap: str,
    capture_mechanism: str,
    time_window: dict,
) -> str:
    payload = {
        "sector": _normalize_text(sector),
        "problem_or_gap": _normalize_text(problem_or_gap),
        "capture_mechanism": _normalize_text(capture_mechanism),
        "time_window": _normalize_json(time_window),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def create_or_get_opportunity(
    repository: DomainRepository,
    *,
    creator_id: str,
    discovered_by_universe_id: str,
    sector: str,
    problem_or_gap: str,
    capture_mechanism: str,
    evidence_refs: list[str],
    time_window: dict,
    correlation_id: str,
) -> Opportunity:
    if not evidence_refs:
        raise ValueError("opportunity evidence_refs are required")

    universe = await repository.get(Universe, discovered_by_universe_id)
    if universe is None:
        raise NotFoundError("Universe not found")

    fingerprint = normalize_opportunity_fingerprint(
        sector=sector,
        problem_or_gap=problem_or_gap,
        capture_mechanism=capture_mechanism,
        time_window=time_window,
    )
    existing = await repository.opportunity_by_fingerprint(creator_id, fingerprint)
    if existing is not None:
        merged_evidence = list(dict.fromkeys([*existing.evidence_refs_json, *evidence_refs]))
        if merged_evidence != existing.evidence_refs_json:
            existing.evidence_refs_json = merged_evidence
            await repository.session.flush()
            await repository.add_event(
                "opportunity_rediscovered",
                "opportunity",
                existing.id,
                discovered_by_universe_id,
                "universe",
                correlation_id,
                {"evidence_refs": evidence_refs},
            )
            await repository.commit()
        return existing

    candidate = Opportunity(
        creator_id=creator_id,
        fingerprint=fingerprint,
        sector=sector.strip(),
        problem_or_gap=" ".join(problem_or_gap.split()),
        capture_mechanism=" ".join(capture_mechanism.split()),
        evidence_refs_json=list(dict.fromkeys(evidence_refs)),
        first_discovered_by_universe_id=discovered_by_universe_id,
        time_window_json=_normalize_json(time_window),
        status="DETECTED",
    )
    try:
        item = await repository.add(candidate)
    except IntegrityError as exc:
        await repository.rollback()
        if _integrity_constraint_name(exc) != "uq_opportunity_creator_fingerprint":
            raise
        winner = await repository.opportunity_by_fingerprint(creator_id, fingerprint)
        if winner is None:
            raise
        merged_evidence = list(dict.fromkeys([*winner.evidence_refs_json, *evidence_refs]))
        if merged_evidence != winner.evidence_refs_json:
            winner.evidence_refs_json = merged_evidence
            await repository.session.flush()
        await repository.add_event(
            "opportunity_rediscovered",
            "opportunity",
            winner.id,
            discovered_by_universe_id,
            "universe",
            correlation_id,
            {"evidence_refs": evidence_refs, "dedupe_race": True},
        )
        await repository.commit()
        return winner

    await repository.add_event(
        "opportunity_detected",
        "opportunity",
        item.id,
        discovered_by_universe_id,
        "universe",
        correlation_id,
        {"fingerprint": fingerprint, "sector": item.sector},
    )
    await repository.commit()
    return item


async def submit_thesis(
    repository: DomainRepository,
    *,
    opportunity_id: str,
    universe_id: str,
    thesis: OpportunityThesisCreate,
    correlation_id: str,
) -> OpportunityThesis:
    opportunity = await repository.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.creator_id != thesis.creator_id:
        raise NotFoundError("Opportunity not found")
    universe = await repository.get(Universe, universe_id)
    if universe is None:
        raise NotFoundError("Universe not found")

    item = await repository.add(
        OpportunityThesis(
            opportunity_id=opportunity.id,
            universe_id=universe.id,
            proposed_value=thesis.proposed_value,
            target_payer=thesis.target_payer,
            capture_path=thesis.capture_path,
            estimated_cost_json=thesis.estimated_cost,
            expected_value_json=thesis.expected_value,
            max_downside_json=thesis.max_downside,
            confidence=thesis.confidence,
            falsification_conditions_json=thesis.falsification_conditions,
            evidence_refs_json=thesis.evidence_refs,
            status="PROPOSED",
        )
    )
    await repository.add_event(
        "opportunity_thesis_submitted",
        "opportunity",
        opportunity.id,
        universe.id,
        "universe",
        correlation_id,
        {"thesis_id": item.id, "confidence": item.confidence},
    )
    await repository.commit()
    return item


class LeaseConflictError(RuntimeError):
    """Raised when an exclusive executive lease cannot be acquired."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(getattr(exc, "orig", None), "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    if name:
        return str(name)
    message = str(exc)
    for candidate in (
        "uq_opportunity_creator_fingerprint",
        "uq_opportunity_active_executive_lease",
        "ix_missions_opportunity_id",
    ):
        if candidate in message:
            return candidate
    return None


def _is_executive_lease_conflict(exc: IntegrityError) -> bool:
    constraint_name = _integrity_constraint_name(exc)
    if constraint_name == "uq_opportunity_active_executive_lease":
        return True
    return "uq_opportunity_active_executive_lease" in str(exc)


async def _validated_competition_entities(
    repository: DomainRepository,
    *,
    opportunity_id: str,
    thesis_id: str,
    universe_id: str,
    lock_opportunity: bool,
) -> tuple[Opportunity, OpportunityThesis, Universe]:
    opportunity = (
        await repository.get_for_update(Opportunity, opportunity_id)
        if lock_opportunity
        else await repository.get(Opportunity, opportunity_id)
    )
    if opportunity is None:
        raise NotFoundError("Opportunity not found")

    thesis = await repository.get(OpportunityThesis, thesis_id)
    if thesis is None or thesis.opportunity_id != opportunity.id:
        raise NotFoundError("Opportunity thesis not found")

    universe = await repository.get(Universe, universe_id)
    if universe is None or thesis.universe_id != universe.id:
        raise NotFoundError("Universe not found for thesis")

    return opportunity, thesis, universe


async def acquire_research_lease(
    repository: DomainRepository,
    *,
    opportunity_id: str,
    thesis_id: str,
    universe_id: str,
    expires_at: datetime,
    correlation_id: str,
) -> OpportunityLease:
    now = _utcnow()
    if expires_at <= now:
        raise ValueError("lease expires_at must be in the future")

    opportunity, thesis, universe = await _validated_competition_entities(
        repository,
        opportunity_id=opportunity_id,
        thesis_id=thesis_id,
        universe_id=universe_id,
        lock_opportunity=False,
    )
    lease = await repository.add(
        OpportunityLease(
            opportunity_id=opportunity.id,
            thesis_id=thesis.id,
            universe_id=universe.id,
            lease_type="RESEARCH",
            status="ACTIVE",
            expires_at=expires_at,
        )
    )
    await repository.add_event(
        "opportunity_lease_acquired",
        "opportunity",
        opportunity.id,
        universe.id,
        "universe",
        correlation_id,
        {"lease_id": lease.id, "lease_type": lease.lease_type, "thesis_id": thesis.id},
    )
    await repository.commit()
    return lease


async def acquire_executive_lease(
    repository: DomainRepository,
    *,
    opportunity_id: str,
    thesis_id: str,
    universe_id: str,
    expires_at: datetime,
    correlation_id: str,
) -> OpportunityLease:
    now = _utcnow()
    if expires_at <= now:
        raise ValueError("lease expires_at must be in the future")

    opportunity, thesis, universe = await _validated_competition_entities(
        repository,
        opportunity_id=opportunity_id,
        thesis_id=thesis_id,
        universe_id=universe_id,
        lock_opportunity=True,
    )

    expired = list(
        (
            await repository.session.scalars(
                select(OpportunityLease)
                .where(
                    OpportunityLease.opportunity_id == opportunity.id,
                    OpportunityLease.lease_type == "EXECUTIVE",
                    OpportunityLease.status == "ACTIVE",
                    OpportunityLease.expires_at <= now,
                )
                .with_for_update()
            )
        ).all()
    )
    for stale in expired:
        stale.status = "EXPIRED"
        stale.released_at = now
        await repository.add_event(
            "opportunity_lease_expired",
            "opportunity",
            opportunity.id,
            stale.universe_id,
            "universe",
            correlation_id,
            {"lease_id": stale.id, "thesis_id": stale.thesis_id},
        )
    if expired:
        await repository.session.flush()

    lease = OpportunityLease(
        opportunity_id=opportunity.id,
        thesis_id=thesis.id,
        universe_id=universe.id,
        lease_type="EXECUTIVE",
        status="ACTIVE",
        expires_at=expires_at,
    )
    try:
        lease = await repository.add(lease)
    except IntegrityError as exc:
        await repository.rollback()
        if _is_executive_lease_conflict(exc):
            raise LeaseConflictError("an active executive lease already exists") from exc
        raise

    await repository.add_event(
        "opportunity_lease_acquired",
        "opportunity",
        opportunity.id,
        universe.id,
        "universe",
        correlation_id,
        {"lease_id": lease.id, "lease_type": lease.lease_type, "thesis_id": thesis.id},
    )
    await repository.commit()
    return lease


async def release_lease(
    repository: DomainRepository,
    *,
    lease_id: str,
    universe_id: str,
    correlation_id: str,
) -> OpportunityLease:
    lease = await repository.get_for_update(OpportunityLease, lease_id)
    if lease is None or lease.universe_id != universe_id:
        raise NotFoundError("Opportunity lease not found")

    universe = await repository.get(Universe, universe_id)
    if universe is None:
        raise NotFoundError("Universe not found")

    if lease.status == "ACTIVE":
        lease.status = "RELEASED"
        lease.released_at = _utcnow()
        await repository.session.flush()
        await repository.add_event(
            "opportunity_lease_released",
            "opportunity",
            lease.opportunity_id,
            universe.id,
            "universe",
            correlation_id,
            {"lease_id": lease.id, "lease_type": lease.lease_type, "thesis_id": lease.thesis_id},
        )
        await repository.commit()
    return lease


async def select_thesis(
    repository: DomainRepository,
    *,
    opportunity_id: str,
    thesis_id: str,
    correlation_id: str,
) -> OpportunityThesis:
    opportunity = await repository.get_for_update(Opportunity, opportunity_id)
    if opportunity is None:
        raise NotFoundError("Opportunity not found")

    thesis = await repository.get(OpportunityThesis, thesis_id)
    if thesis is None or thesis.opportunity_id != opportunity.id:
        raise NotFoundError("Opportunity thesis not found")

    universe = await repository.get(Universe, thesis.universe_id)
    if universe is None:
        raise NotFoundError("Universe not found")

    previously_selected = list(
        (
            await repository.session.scalars(
                select(OpportunityThesis).where(
                    OpportunityThesis.opportunity_id == opportunity.id,
                    OpportunityThesis.status == "SELECTED",
                    OpportunityThesis.id != thesis.id,
                )
            )
        ).all()
    )
    for previous in previously_selected:
        previous.status = "PROPOSED"

    thesis.status = "SELECTED"
    opportunity.status = "SELECTED"
    await repository.session.flush()
    await repository.add_event(
        "opportunity_thesis_selected",
        "opportunity",
        opportunity.id,
        universe.id,
        "universe",
        correlation_id,
        {"thesis_id": thesis.id},
    )
    await repository.commit()
    return thesis


async def resolve_competition(
    repository: DomainRepository,
    *,
    opportunity_id: str,
    scores: dict[str, float],
    expires_at: datetime,
    correlation_id: str,
) -> tuple[OpportunityThesis, OpportunityLease]:
    """Select one thesis and grant one executive lease in a single transaction.

    Scores are supplied by the competition policy; this function only enforces the
    transactional invariants. The Opportunity row serializes competing resolutions.
    """
    if not scores:
        raise ValueError("competition scores are required")
    normalized_scores: dict[str, float] = {}
    for thesis_id, raw_score in scores.items():
        score = float(raw_score)
        if not math.isfinite(score):
            raise ValueError("competition scores must be finite")
        normalized_scores[str(thesis_id)] = score
    if expires_at <= _utcnow():
        raise ValueError("lease expires_at must be in the future")

    opportunity = await repository.get_for_update(Opportunity, opportunity_id)
    if opportunity is None:
        raise NotFoundError("Opportunity not found")

    theses = list(
        (
            await repository.session.scalars(
                select(OpportunityThesis)
                .where(
                    OpportunityThesis.opportunity_id == opportunity.id,
                    OpportunityThesis.id.in_(list(normalized_scores)),
                )
                .with_for_update()
            )
        ).all()
    )
    by_id = {item.id: item for item in theses}
    unknown = set(normalized_scores) - set(by_id)
    if unknown:
        raise ValueError("competition scores reference unknown theses")

    # Deterministic tie break: higher policy score, then higher thesis confidence,
    # then stable id. The policy decides the score; storage only makes the result stable.
    winner = max(
        theses,
        key=lambda item: (normalized_scores[item.id], item.confidence, item.id),
    )

    now = _utcnow()
    active_leases = list(
        (
            await repository.session.scalars(
                select(OpportunityLease)
                .where(
                    OpportunityLease.opportunity_id == opportunity.id,
                    OpportunityLease.lease_type == "EXECUTIVE",
                    OpportunityLease.status == "ACTIVE",
                )
                .with_for_update()
            )
        ).all()
    )
    current: OpportunityLease | None = None
    for lease in active_leases:
        if lease.expires_at <= now:
            lease.status = "EXPIRED"
            lease.released_at = now
            await repository.add_event(
                "opportunity_lease_expired",
                "opportunity",
                opportunity.id,
                lease.universe_id,
                "universe",
                correlation_id,
                {"lease_id": lease.id, "thesis_id": lease.thesis_id},
            )
        elif lease.thesis_id == winner.id and lease.universe_id == winner.universe_id:
            current = lease
        else:
            raise LeaseConflictError("an active executive lease already exists")

    for thesis in theses:
        thesis.status = "SELECTED" if thesis.id == winner.id else "PROPOSED"
    opportunity.status = "SELECTED"

    if current is None:
        current = OpportunityLease(
            opportunity_id=opportunity.id,
            thesis_id=winner.id,
            universe_id=winner.universe_id,
            lease_type="EXECUTIVE",
            status="ACTIVE",
            expires_at=expires_at,
        )
        repository.session.add(current)

    await repository.add_event(
        "opportunity_competition_resolved",
        "opportunity",
        opportunity.id,
        winner.universe_id,
        "universe",
        correlation_id,
        {
            "winner_thesis_id": winner.id,
            "scores": normalized_scores,
            "executive_lease_id": current.id,
        },
    )
    await repository.session.flush()
    await repository.commit()
    return winner, current


async def create_mission_from_opportunity(
    repository: DomainRepository,
    *,
    creator_id: str,
    opportunity_id: str,
    thesis_id: str,
    executive_lease_id: str,
    title: str,
    objective: str,
    authorization: dict,
    correlation_id: str,
) -> Mission:
    """Create the single Mission for a selected, exclusively leased Opportunity.

    Opportunity selection and capital never grant authority by themselves. The caller
    supplies the pre-existing Mission authorization envelope, while downstream execution
    remains the normal Mission/AgentRuntime/CapabilityRuntime path.
    """
    opportunity = await repository.get_for_update(Opportunity, opportunity_id)
    if opportunity is None or opportunity.creator_id != creator_id:
        raise NotFoundError("Opportunity not found")

    existing = await repository.session.scalar(
        select(Mission).where(Mission.opportunity_id == opportunity.id).with_for_update()
    )
    if existing is not None:
        if existing.creator_id != creator_id:
            raise NotFoundError("Opportunity not found")
        return existing

    thesis = await repository.get(OpportunityThesis, thesis_id)
    if (
        thesis is None
        or thesis.opportunity_id != opportunity.id
        or thesis.status != "SELECTED"
    ):
        raise InvalidOrigin("Opportunity Mission requires the selected thesis")

    lease = await repository.get_for_update(OpportunityLease, executive_lease_id)
    if (
        lease is None
        or lease.opportunity_id != opportunity.id
        or lease.thesis_id != thesis.id
        or lease.universe_id != thesis.universe_id
        or lease.lease_type != "EXECUTIVE"
        or lease.status != "ACTIVE"
    ):
        raise InvalidOrigin("Opportunity Mission requires its active executive lease")

    now = _utcnow()
    if lease.expires_at <= now:
        lease.status = "EXPIRED"
        lease.released_at = now
        await repository.add_event(
            "opportunity_lease_expired",
            "opportunity",
            opportunity.id,
            lease.universe_id,
            "universe",
            correlation_id,
            {"lease_id": lease.id, "thesis_id": lease.thesis_id},
        )
        await repository.commit()
        raise InvalidOrigin("Opportunity executive lease has expired")

    if not isinstance(authorization, dict):
        raise ValueError("authorization must be a mapping")

    try:
        mission = await repository.add(
            Mission(
                inception_id=None,
                opportunity_id=opportunity.id,
                creator_id=creator_id,
                title=title,
                objective=objective,
                status=MissionStatus.DRAFTED.value,
                authorization_json=dict(authorization),
            )
        )
    except IntegrityError as exc:
        await repository.rollback()
        if _integrity_constraint_name(exc) != "ix_missions_opportunity_id":
            raise
        winner = await repository.session.scalar(
            select(Mission).where(Mission.opportunity_id == opportunity.id)
        )
        if winner is None or winner.creator_id != creator_id:
            raise
        return winner
    await repository.add_event(
        "opportunity_mission_created",
        "mission",
        mission.id,
        creator_id,
        "creator",
        correlation_id,
        {
            "opportunity_id": opportunity.id,
            "thesis_id": thesis.id,
            "executive_lease_id": lease.id,
            "universe_id": thesis.universe_id,
        },
    )
    await repository.commit()
    return mission



_LEARNING_FORBIDDEN_KEYS = frozenset({
    "authorization",
    "authorization_json",
    "allowed_capabilities",
    "denied_capabilities",
    "creator_constraints",
    "risk_ceiling",
    "budget",
    "external_effects_allowed",
    "security_policy",
})


def _learning_safe_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in _LEARNING_FORBIDDEN_KEYS
    }


def _learning_signal(outcome: dict[str, Any]) -> float:
    raw_reward = outcome.get("reward")
    if isinstance(raw_reward, (int, float)):
        return max(-1.0, min(1.0, float(raw_reward)))
    return 1.0 if bool(outcome.get("success")) else -1.0


async def record_learning_episode(
    repository: DomainRepository,
    *,
    universe_id: str,
    source: str,
    strategy: dict,
    outcome: dict,
    correlation_id: str,
) -> UniverseMemory:
    universe = await repository.get(Universe, universe_id)
    if universe is None:
        raise NotFoundError("Universe not found")
    source = source.strip()
    if not source:
        raise ValueError("learning source is required")

    safe_strategy = _learning_safe_mapping(dict(strategy))
    safe_outcome = _learning_safe_mapping(dict(outcome))
    signal = _learning_signal(safe_outcome)
    key = "perception_learning_v1"

    entry = await repository.session.scalar(
        select(UniverseMemory)
        .where(UniverseMemory.universe_id == universe.id, UniverseMemory.key == key)
        .with_for_update()
    )
    if entry is None:
        value: dict[str, Any] = {
            "episodes": [],
            "provider_preferences": {},
            "sensor_preferences": {},
            "detector_weights": {},
        }
    else:
        value = dict(entry.value_json or {})
        value.setdefault("episodes", [])
        value.setdefault("provider_preferences", {})
        value.setdefault("sensor_preferences", {})
        value.setdefault("detector_weights", {})

    episode = {
        "source": source,
        "strategy": safe_strategy,
        "outcome": safe_outcome,
        "signal": signal,
        "recorded_at": _utcnow().isoformat(),
    }
    episodes = list(value["episodes"])
    episodes.append(episode)
    value["episodes"] = episodes[-100:]

    for strategy_key, target_key in (
        ("provider", "provider_preferences"),
        ("sensor", "sensor_preferences"),
        ("detector", "detector_weights"),
    ):
        selected = safe_strategy.get(strategy_key)
        if isinstance(selected, str) and selected.strip():
            preferences = dict(value[target_key])
            name = selected.strip()
            preferences[name] = round(float(preferences.get(name, 0.0)) + signal, 6)
            value[target_key] = preferences

    if entry is None:
        created = await repository.add(
            UniverseMemory(universe_id=universe.id, key=key, value_json=value)
        )
        if not isinstance(created, UniverseMemory):
            raise TypeError("repository returned an invalid UniverseMemory")
        memory = created
    else:
        entry.value_json = value
        entry.updated_at = _utcnow()
        await repository.session.flush()
        memory = entry

    await repository.add_event(
        "learning_episode_recorded",
        "universe_memory",
        memory.id,
        universe.id,
        "universe",
        correlation_id,
        {
            "source": source,
            "signal": signal,
            "provider": safe_strategy.get("provider"),
            "sensor": safe_strategy.get("sensor"),
            "detector": safe_strategy.get("detector"),
        },
    )
    await repository.commit()
    return memory
