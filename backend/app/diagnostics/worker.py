from __future__ import annotations

import asyncio
import fcntl
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Literal

import httpx
from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.diagnostics.contracts import Observation, ProbeOutcome, ProbeResult, ProbeStatus
from app.diagnostics.heartbeat import ServiceHeartbeat, supervised
from app.diagnostics.incidents import record_incident_evidence
from app.diagnostics.journal import DiagnosticJournal, JournalFull
from app.diagnostics.rules import DiagnosticRules
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeService
from app.models.entities import Chronicle, Creator, Task, Universe
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeOutbox,
    KnowledgeReceipt,
    KnowledgeRevision,
)
from app.models.projection import ProjectionCheckpoint
from app.projections.system import (
    AGENT_PROJECTION,
    MEMORY_PROJECTION,
    MISSION_PROJECTION,
    SYSTEM_PROJECTION,
    TASK_PROJECTION,
)

EXPECTED_PROJECTIONS = (
    SYSTEM_PROJECTION,
    MISSION_PROJECTION,
    TASK_PROJECTION,
    AGENT_PROJECTION,
    MEMORY_PROJECTION,
)
CANONICAL_UNIVERSES = frozenset(
    {
        "knowledge",
        "engineering",
        "security",
        "vision",
        "design",
        "business",
        "marketing",
        "legal",
        "finance",
        "automation",
        "communication",
        "evolution",
    }
)
Probe = Callable[[], Awaitable[bool | None | ProbeOutcome]]

PROBE_RULES = {
    "PostgreSQL": "availability",
    "Redis": "availability",
    "API": "readiness",
    "Fila da memória": "backlog",
    "Disco diagnóstico": "capacity",
    "Projeções do Chronicle": "projection_lag",
    "Tarefas em execução": "task_stall",
    "Universos canônicos": "canonical_universes",
    "Journal diagnóstico": "spool_capacity",
    "Voz local": "local_voice_assets",
    "Inferência": "execution_telemetry",
    "task-worker": "heartbeat",
    "knowledge-worker": "heartbeat",
    "discovery-worker": "heartbeat",
    "opportunity-worker": "heartbeat",
    "stf-training-worker": "heartbeat",
}


def projection_health(head: int, positions: dict[str, int], max_lag: int) -> bool:
    for name in EXPECTED_PROJECTIONS:
        position = positions.get(name)
        if position is None or position < 0 or position > head:
            return False
        if head - position > max_lag:
            return False
    return True


def task_stall_health(
    started_at: Sequence[datetime | None],
    now: datetime,
    stall_seconds: int,
) -> bool:
    limit = timedelta(seconds=stall_seconds)
    return all(started is not None and now - started <= limit for started in started_at)


def universe_health(active_codes: set[str]) -> bool:
    return CANONICAL_UNIVERSES.issubset(active_codes)


def journal_health(root: Path) -> bool:
    return not (root / "spool-full.json").exists()


def local_voice_health(root: Path, enabled: bool) -> bool | None:
    if not enabled:
        return None
    return (
        (root / "kokoro-v1.0.onnx").is_file()
        and (root / "voices-v1.0.bin").is_file()
        and (root / "vosk-pt").is_dir()
    )


async def collect() -> dict[str, ProbeResult]:
    async def db_probe() -> bool:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True

    async def redis_probe() -> bool:
        redis = Redis.from_url(
            settings.redis_url,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        try:
            return bool(await redis.ping())
        finally:
            await redis.aclose()

    async def api_probe() -> bool:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(
                os.environ.get("DIAGNOSTICS_API_URL", "http://api:8000")
                + "/api/v1/health/ready"
            )
            response.raise_for_status()
        return True

    async def worker_probe(resource: str) -> bool:
        async with AsyncSessionLocal() as session:
            found = await session.scalar(
                select(ServiceHeartbeat.boot_id)
                .where(
                    ServiceHeartbeat.service == resource,
                    ServiceHeartbeat.valid_until > datetime.now(timezone.utc),
                )
                .limit(1)
            )
        return found is not None

    async def queue_probe() -> ProbeOutcome:
        async with AsyncSessionLocal() as session:
            done = exists(
                select(KnowledgeReceipt.sequence).where(
                    KnowledgeReceipt.sequence == KnowledgeOutbox.sequence,
                    KnowledgeReceipt.consumer == "knowledge",
                )
            )
            pending = int(
                await session.scalar(
                    select(func.count()).select_from(KnowledgeOutbox).where(~done)
                )
                or 0
            )
        return ProbeOutcome(
            value=pending <= 1000,
            safe_evidence={"pending": pending, "threshold": 1000},
        )

    async def disk_probe() -> ProbeOutcome:
        stats = os.statvfs(settings.deus_diagnostics_root)
        free_bytes = int(stats.f_bavail * stats.f_frsize)
        minimum = 64 * 1024 * 1024
        return ProbeOutcome(
            value=free_bytes >= minimum,
            safe_evidence={"free_bytes": free_bytes, "minimum_free_bytes": minimum},
        )

    async def projection_probe() -> ProbeOutcome:
        async with AsyncSessionLocal() as session:
            head = int(await session.scalar(select(func.max(Chronicle.position))) or 0)
            rows = list((await session.scalars(select(ProjectionCheckpoint))).all())
        positions = {row.projection_name: row.position for row in rows}
        healthy = projection_health(
            head,
            positions,
            settings.deus_diagnostics_projection_max_lag,
        )
        missing = [name for name in EXPECTED_PROJECTIONS if name not in positions]
        return ProbeOutcome(
            value=healthy,
            safe_evidence={
                "chronicle_head": head,
                "checkpoint_count": len(positions),
                "missing": ",".join(missing),
                "max_lag": settings.deus_diagnostics_projection_max_lag,
            },
        )

    async def task_probe() -> ProbeOutcome:
        async with AsyncSessionLocal() as session:
            starts = list(
                (
                    await session.scalars(
                        select(Task.started_at).where(Task.status == "RUNNING")
                    )
                ).all()
            )
        now = datetime.now(timezone.utc)
        healthy = task_stall_health(
            starts,
            now,
            settings.deus_diagnostics_task_stall_seconds,
        )
        ages = [
            max(0, int((now - started).total_seconds()))
            for started in starts
            if started is not None
        ]
        return ProbeOutcome(
            value=healthy,
            safe_evidence={
                "running_tasks": len(starts),
                "oldest_running_seconds": max(ages, default=0),
                "stall_threshold_seconds": settings.deus_diagnostics_task_stall_seconds,
            },
        )

    async def universe_probe() -> ProbeOutcome:
        async with AsyncSessionLocal() as session:
            codes = set(
                (
                    await session.scalars(
                        select(Universe.code).where(Universe.active.is_(True))
                    )
                ).all()
            )
        missing = sorted(CANONICAL_UNIVERSES - codes)
        return ProbeOutcome(
            value=not missing,
            safe_evidence={
                "active_canonical": len(CANONICAL_UNIVERSES) - len(missing),
                "required": len(CANONICAL_UNIVERSES),
                "missing": ",".join(missing),
            },
        )

    async def journal_probe() -> ProbeOutcome:
        health = DiagnosticJournal(Path(settings.deus_diagnostics_root)).health()
        return ProbeOutcome(
            value=not bool(health["spool_full"]),
            safe_evidence=health,
        )

    async def voice_probe() -> ProbeOutcome:
        enabled = settings.deus_voice_session_enabled
        ready = local_voice_health(
            Path(settings.deus_local_voice_models_dir),
            enabled,
        )
        return ProbeOutcome(
            value=ready,
            safe_evidence={
                "runtime": "local",
                "enabled": enabled,
                "models_ready": ready if enabled else None,
            },
        )

    async def inference_probe() -> ProbeOutcome:
        # Provider health would perform a network call. Diagnostics must not manufacture
        # health traffic or spend quota; until execution telemetry is persisted, be honest.
        return ProbeOutcome(
            value=None,
            safe_evidence={"reason": "no_persisted_execution_telemetry"},
        )

    async def bounded(call: Probe) -> ProbeResult:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(2):
                raw = await call()
            outcome = raw if isinstance(raw, ProbeOutcome) else ProbeOutcome(value=raw)
            status: ProbeStatus = (
                "healthy"
                if outcome.value is True
                else "unhealthy"
                if outcome.value is False
                else "unknown"
            )
            evidence = outcome.safe_evidence
        except Exception as exc:
            status = "unhealthy"
            evidence = {"error_type": type(exc).__name__}
        return ProbeResult(
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000),
            safe_evidence=evidence,
        )

    probes: dict[str, Probe] = {
        "PostgreSQL": db_probe,
        "Redis": redis_probe,
        "API": api_probe,
        "Fila da memória": queue_probe,
        "Disco diagnóstico": disk_probe,
        "Projeções do Chronicle": projection_probe,
        "Tarefas em execução": task_probe,
        "Universos canônicos": universe_probe,
        "Journal diagnóstico": journal_probe,
        "Voz local": voice_probe,
        "Inferência": inference_probe,
    }
    if settings.deus_diagnostics_enabled:
        for resource in ["task-worker", "knowledge-worker"]:
            probes[resource] = partial(worker_probe, resource)
        if settings.deus_autonomy_discovery_enabled:
            probes["discovery-worker"] = partial(worker_probe, "discovery-worker")
        if settings.deus_autonomy_competition_enabled:
            probes["opportunity-worker"] = partial(worker_probe, "opportunity-worker")
        if settings.stf_auto_training_enabled:
            probes["stf-training-worker"] = partial(worker_probe, "stf-training-worker")

    values = await asyncio.gather(*(bounded(probe) for probe in probes.values()))
    return dict(zip(probes, values))


async def creator_scope() -> str | None:
    async with AsyncSessionLocal() as session:
        if settings.sovereign_creator_id:
            return await session.scalar(
                select(Creator.id).where(
                    Creator.id == settings.sovereign_creator_id,
                    Creator.is_active.is_(True),
                )
            )
        ids = list(
            await session.scalars(
                select(Creator.id).where(Creator.is_active.is_(True)).limit(2)
            )
        )
        return ids[0] if len(ids) == 1 else None


async def _current_projection(
    session: AsyncSession,
    creator_id: str,
    resource: str,
    observation_type: str,
    episode_id: str | None = None,
) -> KnowledgeRevision | None:
    rows = list(
        await session.scalars(
            select(KnowledgeRevision)
            .join(
                KnowledgeItem,
                KnowledgeItem.current_revision_id == KnowledgeRevision.id,
            )
            .where(
                KnowledgeItem.creator_id == creator_id,
                KnowledgeItem.active.is_(True),
                KnowledgeRevision.kind == "diagnostic",
            )
        )
    )
    for row in rows:
        try:
            data = json.loads(row.content)
        except (TypeError, ValueError):
            continue
        if data.get("type") != observation_type:
            continue
        if observation_type == "incident":
            if episode_id and data.get("episode_id") == episode_id:
                return row
            if episode_id is None and data.get("resource") == resource:
                return row
            continue
        if data.get("resource") == resource:
            return row
    return None


async def publish(journal: DiagnosticJournal, creator_id: str) -> None:
    for observation in journal.pending():
        async with AsyncSessionLocal() as session:
            valid_until = (
                None
                if observation["type"] == "incident"
                else datetime.fromisoformat(observation["valid_until"])
            )
            scope = Scope(creator_id=creator_id)
            service = KnowledgeService(session)
            identity = (
                observation.get("episode_id")
                if observation["type"] == "incident"
                else observation["resource"]
            )
            projection_key = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "creation:diagnostic:"
                    + creator_id
                    + ":"
                    + str(identity)
                    + ":"
                    + observation["type"],
                )
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "diagnostic-projection:" + projection_key},
            )
            await record_incident_evidence(
                session,
                creator_id=creator_id,
                evidence=observation,
            )
            previous = await _current_projection(
                session,
                creator_id,
                observation["resource"],
                observation["type"],
                observation.get("episode_id"),
            )
            older = (
                previous is not None
                and json.loads(previous.content)["observed_at"]
                >= observation["observed_at"]
            )
            if not older:
                source_type: Literal["diagnostic_incident", "diagnostic_observation"] = (
                    "diagnostic_incident"
                    if observation["type"] == "incident"
                    else "diagnostic_observation"
                )
                await service.write(
                    scope,
                    Candidate(
                        title="Diagnóstico: " + observation["resource"],
                        content=json.dumps(observation, ensure_ascii=False),
                        kind="diagnostic",
                        source_type=source_type,
                        source_id=observation["id"],
                        valid_until=valid_until,
                    ),
                    "diagnostic:" + observation["id"],
                    previous.item_id if previous else None,
                    previous.id if previous else None,
                )
            await session.commit()
        journal.ack(observation["id"])


async def run() -> None:
    if not settings.deus_diagnostics_enabled:
        logger.info("diagnostics disabled by configuration")
        return
    journal = DiagnosticJournal(Path(settings.deus_diagnostics_root))
    rules = DiagnosticRules()
    stored = journal.get_rules()
    for row in stored.values():
        for key in ["observed_at", "valid_until"]:
            if key in row:
                row[key] = datetime.fromisoformat(row[key])
    rules.states = stored

    while True:
        now = datetime.now(timezone.utc)
        observations = await collect()
        for resource, result in observations.items():
            incident = rules.observe(resource, result.healthy, now)
            active_episode = rules.states.get(resource, {}).get("episode_id")
            incident_episode_id = (
                str(active_episode)
                if active_episode
                else str(incident["episode_id"])
                if incident and incident.get("episode_id")
                else None
            )
            observation = Observation(
                id=str(uuid.uuid4()),
                resource=resource,
                rule=PROBE_RULES.get(resource, "availability"),
                status=result.status,
                observed_at=now,
                valid_until=now + timedelta(seconds=45),
                latency_ms=result.latency_ms,
                safe_evidence=result.safe_evidence,
                incident_episode_id=incident_episode_id,
            ).model_dump(mode="json", exclude_none=True)
            try:
                journal.append(observation)
                if incident:
                    journal.append(
                        {
                            **observation,
                            **incident,
                            "id": str(uuid.uuid4()),
                            "type": "incident",
                        }
                    )
            except JournalFull:
                logger.error(
                    "diagnostic journal full; new evidence admission stopped"
                )

        saved = {
            key: {
                k: v.isoformat() if isinstance(v, datetime) else v
                for k, v in row.items()
            }
            for key, row in rules.states.items()
        }
        journal.set_rules(saved)
        try:
            creator_id = await creator_scope()
            if creator_id:
                journal.bind_creator(creator_id)
                await publish(journal, creator_id)
        except Exception as exc:
            logger.bind(
                component="diagnostics",
                error_type=type(exc).__name__,
            ).warning("diagnostics retained locally for replay")
        await asyncio.sleep(15)


if __name__ == "__main__":
    root = Path(settings.deus_diagnostics_root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(supervised("diagnostics-worker", run))
