import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.core.dispatch_state_machine import DispatchState, retry_delay, transition_dispatch
from app.core.domain import DomainError
from app.models.dispatch import DispatchAttempt, DispatchItem
from app.repositories.dispatch import DispatchRepository
from app.services.domain import NotFoundError
from app.services.tree_core import TreeCoreService


class DispatchError(DomainError):
    pass


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class DispatchService:
    def __init__(self, repository: DispatchRepository, matcher: TreeCoreService):
        self.repository = repository
        self.matcher = matcher

    async def enqueue(self, creator_id, task_id, priority, max_attempts):
        task = await self.repository.task(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        mission = await self.repository.mission(task.mission_id)
        if mission is None or mission.creator_id != creator_id:
            raise NotFoundError("Task not found")
        if mission.status != "authorized" or task.state != "ready" or not await self.repository.dependencies_ready(task.id):
            raise DispatchError("Task is not structurally eligible")
        capability = await self.repository.capability(task.required_capability_id)
        if capability is None:
            raise DispatchError("Capability unavailable")
        _, agents = await self.matcher.match(mission.id, [capability.name])
        if not agents:
            raise DispatchError("No compatible agent")
        item = DispatchItem(
            task_id=task.id,
            mission_id=mission.id,
            agent_id=agents[0].id,
            capability_id=capability.id,
            state="queued",
            priority=priority,
            available_at=datetime.now(timezone.utc),
            attempt_count=0,
            max_attempts=max_attempts,
            version=1,
        )
        try:
            await self.repository.add(item)
            await self.repository.add(DispatchAttempt(dispatch_item_id=item.id, attempt_number=0, event_type="enqueued", metadata_json={}))
            await self.repository.commit()
        except IntegrityError as exc:
            raise DispatchError("Task already has an active dispatch") from exc
        return item

    async def get(self, item_id):
        item = await self.repository.get(item_id)
        if item is None:
            raise NotFoundError("Dispatch not found")
        return item

    async def lease(self, worker_id, lease_seconds, capability_ids=None):
        now = datetime.now(timezone.utc)
        for expired in await self.repository.expired_leases(now):
            expired.state = transition_dispatch(expired.state, DispatchState.QUEUED)
            expired.lease_owner = expired.lease_token_hash = expired.leased_at = expired.lease_expires_at = None
            expired.version += 1
        item = (
            await self.repository.acquire(now)
            if capability_ids is None
            else await self.repository.acquire(now, capability_ids)
        )
        if item is None:
            return None, None
        token = secrets.token_urlsafe(32)
        digest = token_hash(token)
        item.state = transition_dispatch(item.state, DispatchState.LEASED)
        item.lease_owner = worker_id
        item.lease_token_hash = digest
        item.leased_at = now
        item.lease_expires_at = now + timedelta(seconds=lease_seconds)
        item.version += 1
        await self.repository.add(
            DispatchAttempt(
                dispatch_item_id=item.id,
                attempt_number=item.attempt_count,
                event_type="leased",
                worker_id=worker_id,
                lease_token_hash=digest,
                metadata_json={},
            )
        )
        await self.repository.commit()
        return item, token

    def _valid(self, item, worker, token):
        return (
            item.state == "leased"
            and item.lease_owner == worker
            and item.lease_token_hash
            and hmac.compare_digest(item.lease_token_hash, token_hash(token))
        )

    async def _leased(self, item_id, worker, token):
        item = await self.repository.get(item_id, lock=True)
        if item is None:
            raise NotFoundError("Dispatch not found")
        if not self._valid(item, worker, token):
            raise DispatchError("Invalid lease")
        expires = item.lease_expires_at
        if expires is None or (expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc):
            raise DispatchError("Lease expired")
        return item

    async def renew(self, item_id, worker, token, seconds):
        item = await self._leased(item_id, worker, token)
        now = datetime.now(timezone.utc)
        if item.lease_expires_at is None or item.lease_expires_at < now:
            raise DispatchError("Lease expired")
        item.lease_expires_at = now + timedelta(seconds=seconds)
        item.version += 1
        await self.repository.commit()
        return item

    async def acknowledge(self, item_id, worker, token):
        item = await self._leased(item_id, worker, token)
        item.state = transition_dispatch(item.state, DispatchState.ACKNOWLEDGED)
        item.acknowledged_at = datetime.now(timezone.utc)
        item.version += 1
        await self.repository.add(
            DispatchAttempt(
                dispatch_item_id=item.id, attempt_number=item.attempt_count, event_type="acknowledged", worker_id=worker, metadata_json={}
            )
        )
        await self.repository.commit()
        return item

    async def fail(self, item_id, worker, token, code, message, base=30, maximum=3600):
        item = await self._leased(item_id, worker, token)
        now = datetime.now(timezone.utc)
        item.attempt_count += 1
        item.last_error_code = code
        item.last_error_message = message
        item.last_failed_at = now
        target = DispatchState.DEAD_LETTERED if item.attempt_count >= item.max_attempts else DispatchState.RETRY_SCHEDULED
        item.state = transition_dispatch(item.state, target)
        if target == DispatchState.DEAD_LETTERED:
            item.dead_lettered_at = now
        else:
            item.available_at = now + timedelta(seconds=retry_delay(base, item.attempt_count, maximum))
        item.lease_owner = item.lease_token_hash = item.leased_at = item.lease_expires_at = None
        item.version += 1
        await self.repository.add(
            DispatchAttempt(
                dispatch_item_id=item.id,
                attempt_number=item.attempt_count,
                event_type=item.state,
                error_code=code,
                error_message=message,
                metadata_json={},
            )
        )
        await self.repository.commit()
        return item

    async def release(self, item_id, worker, token):
        item = await self._leased(item_id, worker, token)
        item.state = transition_dispatch(item.state, DispatchState.QUEUED)
        item.lease_owner = item.lease_token_hash = item.leased_at = item.lease_expires_at = None
        item.version += 1
        await self.repository.commit()
        return item

    async def cancel(self, item_id):
        item = await self.repository.get(item_id, lock=True)
        if item is None:
            raise NotFoundError("Dispatch not found")
        item.state = transition_dispatch(item.state, DispatchState.CANCELLED)
        item.cancelled_at = datetime.now(timezone.utc)
        item.version += 1
        await self.repository.commit()
        return item
