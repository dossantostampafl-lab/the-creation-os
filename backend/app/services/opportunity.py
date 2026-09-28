from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.entities import Universe
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

    item = await repository.add(
        Opportunity(
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
    )
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


def _is_executive_lease_conflict(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
    constraint_name = getattr(constraint_name, "constraint_name", None)
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
