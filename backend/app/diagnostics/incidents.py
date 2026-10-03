from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagnostics import DiagnosticCauseHypothesis, DiagnosticIncident


def incident_fingerprint(creator_id: str, resource: str, rule: str, episode_id: str) -> str:
    raw = f"{creator_id}:{resource}:{rule}:{episode_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _append_observation(existing: list[str], observation_id: str) -> list[str]:
    if observation_id in existing:
        return existing
    return [*existing, observation_id]


async def record_incident_evidence(
    session: AsyncSession,
    *,
    creator_id: str,
    evidence: dict[str, Any],
) -> DiagnosticIncident | None:
    episode_id = evidence.get("episode_id") or evidence.get("incident_episode_id")
    if not episode_id:
        return None

    resource = str(evidence["resource"])
    rule = str(evidence.get("rule") or "availability")
    observed_at = datetime.fromisoformat(str(evidence["observed_at"]))
    observation_id = str(evidence["id"])

    incident = await session.scalar(
        select(DiagnosticIncident).where(
            DiagnosticIncident.id == str(episode_id),
            DiagnosticIncident.creator_id == creator_id,
        )
    )
    if incident is None:
        incident = DiagnosticIncident(
            id=str(episode_id),
            creator_id=creator_id,
            fingerprint=incident_fingerprint(creator_id, resource, rule, str(episode_id)),
            resource=resource,
            rule=rule,
            state="open",
            first_seen=observed_at,
            last_seen=observed_at,
            observation_ids=[observation_id],
        )
        session.add(incident)
        await session.flush()
    else:
        incident.last_seen = max(incident.last_seen, observed_at)
        incident.observation_ids = _append_observation(list(incident.observation_ids or []), observation_id)

    if evidence.get("type") == "incident":
        state = str(evidence.get("state") or incident.state)
        incident.state = state
        if state == "recovered":
            incident.recovered_at = observed_at
    return incident


async def record_cause_hypothesis(
    session: AsyncSession,
    *,
    creator_id: str,
    incident_id: str,
    content: str,
    author_type: str,
    author_id: str | None = None,
    evidence_ids: list[str] | None = None,
) -> DiagnosticCauseHypothesis:
    incident = await session.scalar(
        select(DiagnosticIncident).where(
            DiagnosticIncident.id == incident_id,
            DiagnosticIncident.creator_id == creator_id,
        )
    )
    if incident is None:
        raise ValueError("incident unavailable in Creator scope")
    hypothesis = DiagnosticCauseHypothesis(
        creator_id=creator_id,
        incident_id=incident_id,
        author_type=author_type,
        author_id=author_id,
        status="hypothesis",
        content=content,
        evidence_ids=list(evidence_ids or []),
    )
    session.add(hypothesis)
    await session.flush()
    return hypothesis
