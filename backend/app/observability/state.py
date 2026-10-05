"""Aggregate snapshots run outside requests; exporter callbacks never access the DB."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import Observation
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.entities import Agent, Mission, Task
from app.models.opportunity import Opportunity
from app.models.security_task_force import StfRun

_SNAPSHOT: list[Observation] = []
_LAST_SUCCESS = 0.0
_STATUSES = frozenset({'drafted', 'planned', 'authorized', 'running', 'completed', 'failed',
    'cancelled', 'queued', 'pending', 'active', 'paused', 'idle', 'blocked', 'executing',
    'detected', 'researching', 'selected', 'rejected', 'approved', 'promoted', 'concluded',
    'aborted', 'succeeded', 'ready', 'degraded', 'stopped', 'training', 'available',
    'waiting', 'leased', 'retrying', 'pending_approval'})


def _status(value: Any) -> str:
    if isinstance(value, bool):
        return "active" if value else "paused"
    normalized = str(value).lower()
    return normalized if normalized in _STATUSES else 'other'


def _observations(options: Any):
    return list(_SNAPSHOT)


def _age(options: Any):
    return [Observation(time.monotonic() - _LAST_SUCCESS)] if _LAST_SUCCESS else []


async def monitor_state() -> None:
    from app.config import settings
    if not settings.telemetry_enabled:
        return
    meter = metrics.get_meter(__name__)
    meter.create_observable_gauge('creation.entities', callbacks=[_observations])
    meter.create_observable_gauge('creation.snapshot.age', unit='s', callbacks=[_age])
    global _SNAPSHOT, _LAST_SUCCESS
    while True:
        try:
            observations = []
            async with asyncio.timeout(2), AsyncSessionLocal() as session:
                for domain, model, field in (
                    ('agents', Agent, Agent.active), ('missions', Mission, Mission.status),
                    ('tasks', Task, Task.status), ('opportunity', Opportunity, Opportunity.status),
                    ('cyber_range', StfRun, StfRun.state),
                ):
                    result = await session.execute(select(field, func.count()).group_by(field))
                    counts: dict[str, int] = {}
                    for state, count in result:
                        label = _status(state)
                        counts[label] = counts.get(label, 0) + count
                    for state, count in counts.items():
                        observations.append(Observation(count, {'domain': domain, 'state': state}))
            _SNAPSHOT, _LAST_SUCCESS = observations, time.monotonic()
        except Exception:
            # Keep the last successful snapshot; its age exposes unavailable data.
            pass
        await asyncio.sleep(30)
