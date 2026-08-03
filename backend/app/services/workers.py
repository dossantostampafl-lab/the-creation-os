import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.core.domain import AuthorizationDenied, DomainError
from app.models.dispatch import Worker
from app.repositories.workers import WorkerRepository
from app.services.dispatch import DispatchService
from app.services.domain import NotFoundError

PROTOCOL_MAJOR = "1"
HEARTBEAT_TTL = timedelta(seconds=120)


class WorkerProtocolError(DomainError):
    pass


def credential_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def validate_version(version: str) -> None:
    if version.split(".", 1)[0] != PROTOCOL_MAJOR:
        raise WorkerProtocolError("Incompatible worker protocol version")


class WorkerService:
    def __init__(self, repository: WorkerRepository, dispatch: DispatchService):
        self.repository = repository
        self.dispatch = dispatch

    async def register(self, worker_uuid: str, name: str, version: str, capability_names: list[str]):
        validate_version(version)
        names = sorted({name.strip().lower() for name in capability_names if name.strip()})
        capabilities = []
        for name_ in names:
            capability = await self.repository.capability(name_)
            if capability is None:
                raise WorkerProtocolError(f"Unknown capability: {name_}")
            capabilities.append(capability)
        token = secrets.token_urlsafe(32)
        worker = Worker(
            worker_uuid=worker_uuid,
            worker_name=name,
            version=version,
            credential_hash=credential_hash(token),
            status="registered",
            capabilities=capabilities,
        )
        try:
            await self.repository.add(worker)
            await self.repository.commit()
        except IntegrityError as exc:
            raise WorkerProtocolError("Worker already registered") from exc
        return worker, token

    async def authenticate(self, worker_uuid: str, token: str, lock=False):
        worker = await self.repository.get_by_uuid(worker_uuid, lock=lock)
        if worker is None or not hmac.compare_digest(worker.credential_hash, credential_hash(token)):
            raise AuthorizationDenied("Invalid worker identity")
        if worker.status == "retired":
            raise AuthorizationDenied("Worker is retired")
        validate_version(worker.version)
        return worker

    async def heartbeat(self, worker: Worker, version: str, status: str):
        validate_version(version)
        worker.version = version
        worker.last_heartbeat = datetime.now(timezone.utc)
        worker.status = status
        await self.repository.commit()
        return worker

    async def claim(self, worker: Worker, lease_seconds: int):
        worker = await self.repository.get_by_uuid(worker.worker_uuid, lock=True)
        if worker.status not in {"registered", "available"}:
            raise WorkerProtocolError("Worker is not available")
        if worker.last_heartbeat is None:
            raise WorkerProtocolError("Worker heartbeat required")
        heartbeat = worker.last_heartbeat if worker.last_heartbeat.tzinfo else worker.last_heartbeat.replace(tzinfo=timezone.utc)
        if heartbeat < datetime.now(timezone.utc) - HEARTBEAT_TTL:
            worker.status = "offline"
            await self.repository.commit()
            raise WorkerProtocolError("Worker heartbeat expired")
        item, token = await self.dispatch.lease(worker.worker_uuid, lease_seconds, [x.id for x in worker.capabilities])
        if item is None:
            return None
        worker.status = "busy"
        await self.repository.commit()
        capability = await self.dispatch.repository.capability(item.capability_id)
        return item, token, capability.name

    async def release(self, worker: Worker, dispatch_id: str, token: str):
        item = await self.dispatch.release(dispatch_id, worker.worker_uuid, token)
        worker.status = "available"
        await self.repository.commit()
        return item

    async def acknowledge(self, worker: Worker, dispatch_id: str, token: str):
        item = await self.dispatch.acknowledge(dispatch_id, worker.worker_uuid, token)
        worker.status = "available"
        await self.repository.commit()
        return item

    async def fail(self, worker: Worker, dispatch_id: str, token: str, code: str, message: str, base=30, maximum=3600):
        item = await self.dispatch.fail(dispatch_id, worker.worker_uuid, token, code, message, base=base, maximum=maximum)
        worker.status = "available"
        await self.repository.commit()
        return item

    async def shutdown(self, worker: Worker):
        if await self.repository.active_lease(worker.worker_uuid):
            raise WorkerProtocolError("Worker has an active lease")
        worker.status = "retired"
        await self.repository.commit()
        return worker

    async def get(self, worker_id: str):
        worker = await self.repository.get(worker_id)
        if worker is None:
            raise NotFoundError("Worker not found")
        return worker
