from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models.entities import Universe
from app.models.opportunity import Opportunity, OpportunityThesis
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
