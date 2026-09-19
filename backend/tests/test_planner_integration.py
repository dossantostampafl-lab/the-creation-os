import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from db_safety import create_isolated_test_engine
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db.session import get_session
from app.main import app
from app.models.entities import Capability, Conversation, Creator, Inception, Message, Mission, Task
from app.repositories.planner import PlannerRepository
from app.services.planner import PlannerError, PlannerService

pytestmark = pytest.mark.integration


def auth(subject):
    value = jwt.encode(
        {"sub": subject, "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
async def planner_db():
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.execute(
            text(
                "TRUNCATE task_dependencies, tasks, agent_capabilities, capabilities, chronicles, mission_plans, missions, inceptions, messages, conversations, creator RESTART IDENTITY CASCADE"
            )
        )
    creator_id = str(uuid.uuid4())
    capability_id = str(uuid.uuid4())
    mission_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    inception_id = str(uuid.uuid4())
    async with factory() as s:
        s.add_all(
            [
                Creator(id=creator_id, username="creator", password_hash="unused", is_active=True),
                Capability(id=capability_id, name="planning", description=""),
            ]
        )
        await s.commit()
        s.add(Conversation(id=conversation_id, creator_id=creator_id, title="planner", status="active"))
        await s.commit()
        s.add(
            Message(
                id=message_id,
                conversation_id=conversation_id,
                role="creator",
                actor_id=creator_id,
                correlation_id=str(uuid.uuid4()),
                content="x",
                route="central",
                metadata_json={},
            )
        )
        await s.commit()
        s.add(
            Inception(
                id=inception_id,
                conversation_id=conversation_id,
                source_message_id=message_id,
                title="i",
                description="d",
                status="approved",
                trinity_assessment_json={},
            )
        )
        await s.commit()
        s.add(
            Mission(
                id=mission_id,
                inception_id=inception_id,
                creator_id=creator_id,
                title="m",
                objective="objective",
                status="authorized",
                authorization_json={},
            )
        )
        await s.commit()

    async def override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield factory, creator_id, capability_id, mission_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_all_nine_endpoints_security_and_idempotency(planner_db):
    factory, creator, capability, mission = planner_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get(f"/api/v1/tasks?mission_id={mission}")).status_code == 401
        assert (await c.get(f"/api/v1/tasks?mission_id={mission}", headers=auth(str(uuid.uuid4())))).status_code == 403
        h = auth(creator)
        body = {"mission_id": mission, "required_capability": capability}
        planned = await c.post("/api/v1/tree-core/plan", headers=h, json=body)
        assert planned.status_code == 201
        assert (await c.post("/api/v1/tree-core/plan", headers=h, json=body)).status_code == 409
        tasks = (await c.get(f"/api/v1/tasks?mission_id={mission}", headers=h)).json()
        assert len(tasks) == 4
        task_id = tasks[0]["id"]
        assert (await c.get(f"/api/v1/tasks/{task_id}", headers=h)).status_code == 200
        assert (await c.patch(f"/api/v1/tasks/{task_id}", headers=h, json={"priority": 77})).status_code == 200
        assert (await c.patch(f"/api/v1/tasks/{task_id}", headers=h, json={"state": "ready"})).status_code == 422
        created = await c.post(
            "/api/v1/tasks", headers=h, json={"mission_id": mission, "name": "extra", "description": "d", "required_capability": capability}
        )
        assert created.status_code == 201
        extra = created.json()["id"]
        assert (await c.post(f"/api/v1/tasks/{extra}/dependencies", headers=h, json={"dependency_id": task_id})).status_code == 200
        assert (await c.post(f"/api/v1/tasks/{extra}/dependencies", headers=h, json={"dependency_id": task_id})).status_code == 409
        assert (await c.get(f"/api/v1/tasks/{extra}/graph", headers=h)).status_code == 200
        assert (await c.get(f"/api/v1/tasks/{extra}/topology", headers=h)).status_code == 200
        assert (await c.delete(f"/api/v1/tasks/{extra}/dependencies/{task_id}", headers=h)).status_code == 200
        assert (await c.get("/api/v1/tasks/not-a-uuid", headers=h)).status_code == 422
    async with factory() as s:
        assert (await s.get(Mission, mission)).status == "authorized"


@pytest.mark.asyncio
async def test_concurrent_planner_only_one_wins(planner_db):
    factory, creator, capability, mission = planner_db

    async def plan():
        async with factory() as s:
            try:
                await PlannerService(PlannerRepository(s)).plan(creator, mission, capability)
                return "ok"
            except PlannerError:
                return "conflict"

    assert sorted(await asyncio.gather(plan(), plan())) == ["conflict", "ok"]
    async with factory() as s:
        assert len(list((await s.scalars(select(Task))).all())) == 4


@pytest.mark.asyncio
async def test_planner_error_paths_cycle_and_rollback(planner_db):
    factory, creator, capability, mission = planner_db
    async with factory() as s:
        service = PlannerService(PlannerRepository(s))
        with pytest.raises(Exception, match="Mission not found"):
            await service.plan(creator, str(uuid.uuid4()), capability)
        with pytest.raises(Exception, match="Capability not found"):
            await service.plan(creator, mission, str(uuid.uuid4()))
        common = dict(
            mission_id=mission,
            description="d",
            required_capability_id=capability,
            priority=1,
            retry_limit=1,
            retry_count=0,
            timeout_seconds=10,
            estimated_duration=1,
        )
        one = await service.create_task(creator, parent_task_id=None, name="one", **common)
        two = await service.create_task(creator, parent_task_id=one.id, name="two", **common)
        await service.add_dependency(creator, two.id, one.id)
        with pytest.raises(PlannerError, match="cycle"):
            await service.add_dependency(creator, one.id, two.id)
        assert len(await service.topology(creator, mission)) == 2
        task, predecessors, successors = await service.graph(creator, one.id)
        assert task.id == one.id and not predecessors and successors[0].id == two.id
        await service.patch(creator, one.id, {"priority": 99})
        with pytest.raises(Exception, match="Dependency not found"):
            await service.remove_dependency(creator, one.id, str(uuid.uuid4()))
