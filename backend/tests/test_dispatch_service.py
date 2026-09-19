import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.dispatch import DispatchAttempt
from app.services.dispatch import DispatchError, DispatchService, token_hash
from app.services.domain import NotFoundError


class Repo:
    def __init__(self):
        self.task_item = SimpleNamespace(id="task", mission_id="mission", state="ready", required_capability_id="cap")
        self.mission_item = SimpleNamespace(id="mission", creator_id="creator", status="authorized")
        self.capability_item = SimpleNamespace(id="cap", name="planning")
        self.items = {}
        self.history = []
        self.ready = True
        self.raise_integrity = False

    async def task(self, value):
        return self.task_item if value == "task" else None

    async def mission(self, value, lock=False):
        return self.mission_item if value == "mission" else None

    async def add_event(self, *args, **kwargs):
        return None

    async def capability(self, value):
        return self.capability_item if value == "cap" else None

    async def dependencies_ready(self, value):
        return self.ready

    async def add(self, value):
        if self.raise_integrity:
            raise IntegrityError("x", {}, Exception())
        if getattr(value, "id", None) is None:
            value.id = str(uuid.uuid4())
        if isinstance(value, DispatchAttempt):
            self.history.append(value)
        else:
            self.items[value.id] = value
        return value

    async def commit(self):
        return None

    async def get(self, value, lock=False):
        return self.items.get(value)

    async def acquire(self, now):
        return next((x for x in self.items.values() if x.state in {"queued", "retry_scheduled"} and x.available_at <= now), None)

    async def expired_leases(self, now):
        return [x for x in self.items.values() if x.state == "leased" and x.lease_expires_at < now]


class Matcher:
    def __init__(self):
        self.agents = [SimpleNamespace(id="agent")]

    async def match(self, *args):
        return SimpleNamespace(), self.agents


@pytest.fixture
def service():
    repo = Repo()
    return DispatchService(repo, Matcher()), repo


@pytest.mark.asyncio
async def test_enqueue_all_guards(service):
    svc, repo = service
    with pytest.raises(NotFoundError):
        await svc.enqueue("creator", "missing", 0, 3)
    repo.mission_item.creator_id = "other"
    with pytest.raises(NotFoundError):
        await svc.enqueue("creator", "task", 0, 3)
    repo.mission_item.creator_id = "creator"
    repo.ready = False
    with pytest.raises(DispatchError):
        await svc.enqueue("creator", "task", 0, 3)
    repo.ready = True
    repo.capability_item = None
    with pytest.raises(DispatchError, match="Capability"):
        await svc.enqueue("creator", "task", 0, 3)
    repo.capability_item = SimpleNamespace(id="cap", name="planning")
    svc.matcher.agents = []
    with pytest.raises(DispatchError, match="compatible"):
        await svc.enqueue("creator", "task", 0, 3)
    svc.matcher.agents = [SimpleNamespace(id="agent")]
    repo.raise_integrity = True
    with pytest.raises(DispatchError, match="active"):
        await svc.enqueue("creator", "task", 0, 3)


@pytest.mark.asyncio
async def test_lease_commands_retry_dead_letter_and_not_found(service):
    svc, repo = service
    item = await svc.enqueue("creator", "task", 1, 2)
    assert await svc.get(item.id) is item
    with pytest.raises(NotFoundError):
        await svc.get("missing")
    leased, token = await svc.lease("worker", 60)
    assert leased.state == "leased" and leased.lease_token_hash == token_hash(token)
    renewed = await svc.renew(item.id, "worker", token, 120)
    assert renewed.version == 3
    released = await svc.release(item.id, "worker", token)
    assert released.state == "queued"
    leased, token = await svc.lease("worker", 60)
    retry = await svc.fail(item.id, "worker", token, "E", "message", base=10, maximum=100)
    assert retry.state == "retry_scheduled" and retry.attempt_count == 1
    retry.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    leased, token = await svc.lease("worker", 60)
    dead = await svc.fail(item.id, "worker", token, "E2", "message")
    assert dead.state == "dead_lettered" and dead.dead_lettered_at
    with pytest.raises(NotFoundError):
        await svc.cancel("missing")


@pytest.mark.asyncio
async def test_ack_cancel_expiration_and_invalid_tokens(service):
    svc, repo = service
    item = await svc.enqueue("creator", "task", 0, 3)
    _, token = await svc.lease("worker", 60)
    with pytest.raises(DispatchError):
        await svc.acknowledge(item.id, "other", token)
    assert (await svc.acknowledge(item.id, "worker", token)).state == "acknowledged"
    repo.items.clear()
    item = await svc.enqueue("creator", "task", 0, 3)
    _, token = await svc.lease("worker", 60)
    item.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(DispatchError, match="expired"):
        await svc.renew(item.id, "worker", token, 10)
    recovered, new = await svc.lease("new", 60)
    assert recovered.id == item.id and new != token
    await svc.release(item.id, "new", new)
    assert (await svc.cancel(item.id)).state == "cancelled"
