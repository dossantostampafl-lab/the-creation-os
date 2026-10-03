from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import actor
from app.config import settings
from app.core.domain import Actor

router = APIRouter(prefix='/cyber-range', tags=['cyber-range'])

class StartRequest(BaseModel):
    scenario_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')

async def controller_call(method: str, path: str) -> dict[str, Any]:
    if not settings.cyber_range_controller_url:
        raise HTTPException(503, 'Cyber Range não iniciado/configurado no host')
    headers = {}
    if settings.cyber_range_control_token:
        headers['Authorization'] = 'Bearer ' + settings.cyber_range_control_token.get_secret_value()
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.request(method, settings.cyber_range_controller_url.rstrip('/') + path, headers=headers)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, 'Controlador do laboratório indisponível; verifique o host') from exc

@router.get('/status')
async def status(a: Actor = Depends(actor)):
    if not settings.cyber_range_controller_url:
        return {'status':'not_configured','scenarios':[], 'message':'Inicie o laboratório isolado no host para habilitar o Cyber Range.'}
    state = await controller_call('GET', '/state')
    scenarios = await controller_call('GET', '/scenarios')
    return {'status':'available', **state, 'catalog':scenarios['scenarios']}

@router.post('/start')
async def start(body: StartRequest, a: Actor = Depends(actor)):
    if '..' in body.scenario_id or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', body.scenario_id):
        raise HTTPException(422, 'Invalid scenario')
    return await controller_call('POST', '/scenarios/' + body.scenario_id + '/start')

@router.post('/reset')
async def reset(a: Actor = Depends(actor)):
    return await controller_call('POST', '/reset')

@router.post('/snapshots')
async def snapshot(a: Actor = Depends(actor)):
    return await controller_call('POST', '/snapshots')

@router.get('/snapshots')
async def snapshots(a: Actor = Depends(actor)):
    return await controller_call('GET', '/snapshots')
