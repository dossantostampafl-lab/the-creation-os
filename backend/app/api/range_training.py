"""Creator controls for the fixed private training campaign."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cyber_range import controller_call
from app.api.dependencies import actor
from app.config import settings
from app.core.domain import Actor
from app.db.session import AsyncSessionLocal, get_session
from app.models.entities import Agent
from app.models.security_task_force import StfRun
from app.security_task_force.training import (
    TRAINING_AGENT_SPECS,
    AutomaticRangeTraining,
    training_run_filter,
)

router = APIRouter(prefix='/cyber-range/training', tags=['cyber-range'])


class TrainingRequest(BaseModel):
    agent_code: str

    @field_validator('agent_code')
    @classmethod
    def canonical_agent(cls, value: str) -> str:
        if value not in {spec.code for spec in TRAINING_AGENT_SPECS}:
            raise ValueError('Unknown training agent')
        return value


@router.get('')
async def training_status(a: Actor = Depends(actor), session: AsyncSession = Depends(get_session)):
    codes = [spec.code for spec in TRAINING_AGENT_SPECS]
    agents = {agent.code: agent for agent in (await session.scalars(select(Agent).where(Agent.code.in_(codes)))).all()}
    runs = (await session.scalars(select(StfRun).where(
        StfRun.creator_id == a.id,
        training_run_filter(),
    ).order_by(StfRun.created_at.desc()).limit(50))).all()
    # The scheduler considers every unfinished run, independently of recent history.
    active = await session.scalar(select(StfRun).where(
        training_run_filter(),
        StfRun.state.notin_(('COMPLETED', 'ABORTED')),
    ).order_by(StfRun.created_at.asc()).limit(1))
    def run_view(run: StfRun):
        return {'id': run.id, 'mission_id': run.mission_id, 'state': run.state,
                'desired_state': run.desired_state, 'created_at': run.created_at.isoformat()}
    return {
        'range_busy': active is not None,
        'active_run': run_view(active) if active is not None and active.creator_id == a.id else None,
        'worker_enabled': settings.stf_auto_training_enabled,
        'controller_configured': bool(settings.cyber_range_controller_url),
        'environment': 'cyber_range:lab-a',
        'agents': [{
            'id': agents[spec.code].id if spec.code in agents else None,
            'code': spec.code, 'name': spec.name, 'cell': spec.cell, 'specialty': spec.specialty,
            'active': agents[spec.code].active if spec.code in agents else False,
            'registered': spec.code in agents,
        } for spec in TRAINING_AGENT_SPECS],
        'runs': [run_view(run) for run in runs],
    }


@router.post('/start')
async def request_training(body: TrainingRequest, a: Actor = Depends(actor)):
    if not settings.stf_auto_training_enabled:
        raise HTTPException(503, 'O worker de treinamento não está habilitado no host.')
    await controller_call('GET', '/scenarios')
    try:
        return await AutomaticRangeTraining(AsyncSessionLocal).run_once(a.id, agent_code=body.agent_code)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
