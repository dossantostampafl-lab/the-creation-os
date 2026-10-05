import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import actor
from app.config import settings
from app.core.domain import Actor


@pytest.mark.asyncio
async def test_training_requires_creator_and_enabled_worker(monkeypatch):
    from app.api.range_training import router

    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post('/cyber-range/training/start', json={'agent_code':'stf-red-recon'})).status_code == 401
        app.dependency_overrides[actor] = lambda: Actor('creator', 'creator')
        monkeypatch.setattr(settings, 'stf_auto_training_enabled', False)
        assert (await client.post('/cyber-range/training/start', json={'agent_code':'stf-red-recon'})).status_code == 503
        assert (await client.post('/cyber-range/training/start', json={'agent_code':'external-agent'})).status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_training_roster_and_manual_start_use_private_campaign(stf_db, monkeypatch):
    import uuid

    from sqlalchemy import select

    from app.api import range_training
    from app.models.entities import Creator, Universe
    from app.security_task_force.training import TRAINING_AGENT_SPECS, ensure_training_agents

    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    async with factory() as session:
        if await session.scalar(select(Universe).where(Universe.code == 'security')) is None:
            session.add(Universe(id=str(uuid.uuid4()), code='security', name='Security', active=True))
            await session.flush()
        agents = await ensure_training_agents(session)
        agents[0].active = False
        session.add(Creator(id=creator_id, username='creator-training-api', password_hash='unused', is_active=True))
        await session.commit()
    async def session_dependency():
        async with factory() as session:
            yield session
    async def controller(method, path):
        assert (method, path) == ('GET', '/scenarios')
        return {'scenarios': []}
    monkeypatch.setattr(range_training, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(range_training, 'controller_call', controller)
    monkeypatch.setattr(settings, 'stf_auto_training_enabled', True)
    app = FastAPI()
    app.include_router(range_training.router)
    app.dependency_overrides[actor] = lambda: Actor(creator_id, 'creator')
    app.dependency_overrides[range_training.get_session] = session_dependency
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            roster = (await client.get('/cyber-range/training')).json()
            assert len(roster['agents']) == 10
            assert roster['environment'] == 'cyber_range:lab-a'
            assert roster['agents'][0]['active'] is False
            assert roster['runs'] == []
            paused = await client.post('/cyber-range/training/start', json={'agent_code': TRAINING_AGENT_SPECS[0].code})
            assert paused.status_code == 409
            started = await client.post('/cyber-range/training/start', json={'agent_code': TRAINING_AGENT_SPECS[1].code})
            assert started.status_code == 200 and started.json()['status'] == 'queued'
            roster = (await client.get('/cyber-range/training')).json()
            assert roster['runs'][0]['state'] == 'QUEUED'
            assert roster['runs'][0]['mission_id'] == 'stf-training:stf-red-recon'
    finally:
        async with factory() as session:
            agents = await ensure_training_agents(session)
            agents[0].active = True
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_old_unfinished_cycle_remains_visible_after_fifty_newer_runs(stf_db):
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.api import range_training
    from app.models.entities import Creator
    from app.models.security_task_force import StfRun

    _, factory = stf_db
    creator_id = str(uuid.uuid4())
    old_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(Creator(id=creator_id, username='creator-old-training', password_hash='unused', is_active=True))
        await session.flush()
        for index in range(51):
            session.add(StfRun(id=old_id if index == 0 else str(uuid.uuid4()), creator_id=creator_id,
                mission_id='stf-training:stf-red-recon', mission_version=1, request_key=f'old-test-{index}',
                request_hash='a'*64, plan_hash='b'*64, plan_json=[], workflow_id=f'old-test-{index}',
                state='QUEUED' if index == 0 else 'COMPLETED', desired_state='RUN',
                created_at=now+timedelta(seconds=index)))
        await session.commit()
    async def session_dependency():
        async with factory() as session:
            yield session
    app = FastAPI()
    app.include_router(range_training.router)
    app.dependency_overrides[actor] = lambda: Actor(creator_id, 'creator')
    app.dependency_overrides[range_training.get_session] = session_dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        state = (await client.get('/cyber-range/training')).json()
        assert len(state['runs']) == 50
        assert all(run['id'] != old_id for run in state['runs'])
        assert state['active_run']['id'] == old_id
        assert state['range_busy'] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_busy_training_post_does_not_expose_another_creators_run(stf_db, monkeypatch):
    import uuid

    from sqlalchemy import select

    from app.api import range_training
    from app.models.entities import Creator, Universe
    from app.security_task_force.training import AutomaticRangeTraining

    _, factory = stf_db
    owner, requester = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        if await session.scalar(select(Universe).where(Universe.code == 'security')) is None:
            session.add(Universe(id=str(uuid.uuid4()), code='security', name='Security', active=True))
        session.add_all([Creator(id=creator, username=f'busy-{creator}', password_hash='unused', is_active=True) for creator in (owner, requester)])
        await session.commit()
    queued = await AutomaticRangeTraining(factory).run_once(owner, agent_code='stf-red-recon')
    assert queued['status'] == 'queued'
    async def controller(method, path):
        return {'scenarios': []}
    async def session_dependency():
        async with factory() as session:
            yield session
    monkeypatch.setattr(range_training, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(range_training, 'controller_call', controller)
    monkeypatch.setattr(settings, 'stf_auto_training_enabled', True)
    app = FastAPI()
    app.include_router(range_training.router)
    app.dependency_overrides[actor] = lambda: Actor(requester, 'creator')
    app.dependency_overrides[range_training.get_session] = session_dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        state = (await client.get('/cyber-range/training')).json()
        assert state['range_busy'] is True and state['active_run'] is None
        response = await client.post('/cyber-range/training/start', json={'agent_code':'stf-red-recon'})
        assert response.status_code == 200
        assert response.json()['status'] == 'busy'
        assert 'run_id' not in response.json() and 'mission_id' not in response.json()
