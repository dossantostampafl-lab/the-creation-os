from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from jose import jwt
from test_deus_http_flow import _router
from test_knowledge import knowledge_db  # noqa: F401

from app.api import deus as deus_api
from app.config import settings
from app.db.session import get_session
from app.knowledge.contracts import Candidate, Scope
from app.knowledge.service import KnowledgeService
from app.main import app
from app.models.entities import Conversation


@pytest.mark.asyncio
async def test_connected_http_uses_memory_and_replays_without_second_model_call(knowledge_db, monkeypatch):  # noqa: F811
    factory, creator_id, _ = knowledge_db
    conversation_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Conversation(id=conversation_id, creator_id=creator_id, title='Connected', status='active'))
        await KnowledgeService(session).write(Scope(creator_id=creator_id), Candidate(title='Decisão da voz', content='Voz Kokoro local'), 'choice')
        await session.commit()
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices':[{'message':{'content':'Kokoro local.'},'finish_reason':'stop'}], 'model':'auto'})
    async def override_session():
        async with factory() as session:
            yield session
    for key, value in [('sovereign_creator_id', creator_id), ('trinity_enabled', False), ('deus_context_retrieval_enabled', True), ('deus_knowledge_ingestion_enabled', True), ('llm_provider','freellmapi')]:
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(deus_api, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(deus_api, 'build_model_router', lambda: _router(handler))
    app.dependency_overrides[get_session] = override_session
    token = jwt.encode({'sub':creator_id,'type':'access','jti':str(uuid.uuid4()),'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.secret_key.get_secret_value(),algorithm='HS256')
    headers = {'Authorization':'Bearer '+token}
    payload = {'content':'Qual voz foi escolhida?', 'request_id':str(uuid.uuid4())}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            url = '/api/v1/conversations/'+conversation_id+'/deus'
            response = await client.post(url, json=payload, headers=headers)
            assert response.status_code==201, response.text
            replay = await client.post(url, json=payload, headers=headers)
            assert replay.json()==response.json()
            denied = await client.get('/api/v1/cyber-range/status')
            assert denied.status_code==401
            status = await client.get('/api/v1/cyber-range/status', headers=headers)
            assert status.status_code==200 and status.json()['status']=='not_configured'
    finally:
        app.dependency_overrides.clear()
    assert len(calls)==1
    assert any('Kokoro' in row['content'] for row in calls[0]['messages'])
