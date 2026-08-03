"""Standalone Agent Dispatcher worker process (v0.4.4 protocol, v0.4.5 execution).

This process is a *client* of the existing dispatch/worker/execution protocol —
it does not reimplement leasing, backoff, reclaim, or hashing; all of that
already lives in DispatchService/WorkerService and is exercised by the
existing test suite. See docs/AUDIT_v0.5.md section 7 for the design note
registered before this file was written.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
import uuid

from app.admin.worker import SYSTEM_WORKER_UUID, SYSTEM_WORKER_VERSION
from app.agents.handlers import HandlerError, default_registry
from app.config import settings
from app.core.consolidation import ConsolidationError
from app.core.domain import AuthorizationDenied
from app.db.session import AsyncSessionLocal
from app.repositories.consolidation import ConsolidationRepository
from app.repositories.decision import DecisionRepository
from app.repositories.dispatch import DispatchRepository
from app.repositories.execution import ExecutionRepository
from app.repositories.manifestation import ManifestationRepository
from app.repositories.tree_core import TreeCoreRepository
from app.repositories.workers import WorkerRepository
from app.services.consolidation import ConsolidationService
from app.services.decision import DecisionError, DecisionService
from app.services.dispatch import DispatchError, DispatchService
from app.services.domain import NotFoundError
from app.services.execution import AgentExecutionService, ExecutionError
from app.services.manifestation import ManifestationError, ManifestationService
from app.services.tree_core import TreeCoreService
from app.services.workers import WorkerProtocolError, WorkerService

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s app.worker: %(message)s")
logger = logging.getLogger("app.worker")

HEARTBEAT_INTERVAL_SECONDS = 30
POLL_INTERVAL_SECONDS = 2

# All three below default to the production values below (60s lease, 30s/3600s
# backoff base/maximum — identical to DispatchService.fail()'s own defaults)
# unless explicitly overridden by environment variable. This exists so
# integration tests can exercise the *real* lease-expiry and retry/backoff
# mechanisms end-to-end (real wall-clock waits, real Postgres rows) with
# practical, still-nonzero timings, instead of either (a) waiting through
# production-length delays (60s lease, 30s/60s/120s.../backoff — impractical
# for a test suite) or (b) silently shrinking a hardcoded constant in a way
# that would drift from production without anyone noticing. See
# ARCHITECTURE.md, Lote: P4/P5 — concorrência real de worker.
WORKER_UUID = os.environ.get("WORKER_UUID", SYSTEM_WORKER_UUID)
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "60"))
DISPATCH_RETRY_BASE_SECONDS = int(os.environ.get("DISPATCH_RETRY_BASE_SECONDS", "30"))
DISPATCH_RETRY_MAXIMUM_SECONDS = int(os.environ.get("DISPATCH_RETRY_MAXIMUM_SECONDS", "3600"))

LIVENESS_FILE = "/tmp/worker-heartbeat"
LIVENESS_MAX_AGE_SECONDS = HEARTBEAT_INTERVAL_SECONDS * 3


def _credential() -> str:
    # WORKER_CREDENTIAL_OVERRIDE lets a test authenticate this process as a
    # freshly `WorkerService.register()`-ed identity (its own worker_uuid +
    # plaintext token), distinct from the single deployed SYSTEM_WORKER_UUID
    # identity — needed to run two independent worker processes against the
    # same database without one clobbering the other's `Worker.status` row.
    override = os.environ.get("WORKER_CREDENTIAL_OVERRIDE")
    if override:
        return override
    if settings.worker_credential is None:
        raise RuntimeError("WORKER_CREDENTIAL_FILE is not configured; nothing for the worker to authenticate with")
    return settings.worker_credential.get_secret_value()


def _services(session):
    dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
    workers = WorkerService(WorkerRepository(session), dispatch)
    execution = AgentExecutionService(
        ExecutionRepository(session),
        dispatch,
        retry_base_seconds=DISPATCH_RETRY_BASE_SECONDS,
        retry_maximum_seconds=DISPATCH_RETRY_MAXIMUM_SECONDS,
    )
    return dispatch, workers, execution


def _touch_liveness() -> None:
    with contextlib.suppress(OSError):
        with open(LIVENESS_FILE, "w", encoding="utf-8") as handle:
            handle.write(str(time.time()))


async def _authenticate():
    async with AsyncSessionLocal() as session:
        _, workers, _ = _services(session)
        return await workers.authenticate(WORKER_UUID, _credential())


async def _heartbeat(status: str) -> None:
    async with AsyncSessionLocal() as session:
        _, workers, _ = _services(session)
        worker = await workers.authenticate(WORKER_UUID, _credential())
        await workers.heartbeat(worker, SYSTEM_WORKER_VERSION, status)
    _touch_liveness()


async def _claim():
    async with AsyncSessionLocal() as session:
        _, workers, _ = _services(session)
        worker = await workers.authenticate(WORKER_UUID, _credential())
        result = await workers.claim(worker, LEASE_SECONDS)
        if result is None:
            return None
        item, token, capability_name = result
        return item.id, item.mission_id, item.task_id, token, capability_name


async def _execute(dispatch_id: str, mission_id: str, token: str, capability_name: str) -> str | None:
    """Runs create -> accept -> run for one claimed dispatch item. Returns the
    terminal execution state ("succeeded"/"failed"/"timed_out"), or None if the
    attempt could not even start (in which case the lease is released so the
    item returns to the queue instead of sitting leased until it expires).

    The handler is resolved from the item's own capability (not hardcoded to
    structured_echo) so each of the deterministic per-Universe handlers actually
    runs for its own capability. See docs/AUDIT_v0.5.md section 10, decision 3."""
    async with AsyncSessionLocal() as session:
        _, workers, execution_service = _services(session)
        worker = await workers.authenticate(WORKER_UUID, _credential())
        try:
            handler = default_registry.resolve_by_capability(capability_name)
        except HandlerError as exc:
            logger.warning("no handler registered for capability %s: %s", capability_name, exc)
            # A missing handler is not transient like a lease race — it means this
            # capability can never succeed until an operator registers one. Route it
            # through fail() (not release()) so it consumes an attempt, ultimately
            # dead-letters, and fails the Mission instead of being immediately
            # reclaimed and looping forever silently. See docs/AUDIT_v0.5.md.
            #
            # Through `workers.fail()`, not `dispatch.fail()` directly: only
            # the former also resets this worker's own `status` back to
            # "available". Calling dispatch.fail() directly (as this used to)
            # left the worker permanently stuck at "busy" from its earlier
            # claim() — status is a WorkerService-level concern, not
            # DispatchService's — so the worker could never claim anything
            # again, including its own next retry of this very item.
            # Confirmed by direct reproduction with a real `python -m
            # app.worker` process; see ARCHITECTURE.md, Lote: P4/P5 —
            # concorrência real de worker.
            with contextlib.suppress(Exception):
                await workers.fail(
                    worker, dispatch_id, token, "no_handler_registered",
                    f"No handler registered for capability {capability_name!r}",
                    base=DISPATCH_RETRY_BASE_SECONDS, maximum=DISPATCH_RETRY_MAXIMUM_SECONDS,
                )
            return None
        try:
            execution = await execution_service.create(worker, dispatch_id, token, handler.name, handler.version)
            await execution_service.accept(execution.id, worker, token)
            result = await execution_service.run(execution.id, worker, token)
            return result.state
        except (ExecutionError, DispatchError, WorkerProtocolError, AuthorizationDenied, NotFoundError) as exc:
            logger.warning("execution attempt failed for dispatch %s: %s", dispatch_id, exc)
            with contextlib.suppress(Exception):
                await workers.release(worker, dispatch_id, token)
            return None


async def _try_close_out_mission(mission_id: str) -> None:
    """Tail orchestration: consolidate -> decide -> manifest. The worker is only the
    trigger — all three calls delegate entirely to the existing idempotent services.
    Each is safe to attempt repeatedly: not-ready-yet and already-failed/cancelled
    missions simply decline (ConsolidationError / AuthorizationDenied) and this
    function returns quietly, to be retried after the next task completes."""
    correlation_id = str(uuid.uuid4())
    try:
        async with AsyncSessionLocal() as session:
            consolidation, _ = await ConsolidationService(ConsolidationRepository(session)).consolidate(
                mission_id, correlation_id=correlation_id, actor_id=SYSTEM_WORKER_UUID, actor_role="worker"
            )
    except (ConsolidationError, AuthorizationDenied, NotFoundError):
        return

    try:
        async with AsyncSessionLocal() as session:
            decision, _ = await DecisionService(DecisionRepository(session)).decide(
                mission_id, correlation_id=correlation_id, actor_id=SYSTEM_WORKER_UUID, actor_role="worker",
                causation_id=consolidation.id,
            )
    except (DecisionError, AuthorizationDenied, NotFoundError):
        return

    try:
        async with AsyncSessionLocal() as session:
            await ManifestationService(ManifestationRepository(session)).manifest(
                mission_id, correlation_id=correlation_id, actor_id=SYSTEM_WORKER_UUID, actor_role="worker",
                causation_id=decision.id,
            )
    except (ManifestationError, AuthorizationDenied, NotFoundError):
        return


class WorkerProcess:
    def __init__(self) -> None:
        self._shutdown_requested = False

    def _request_shutdown(self, *_args) -> None:
        logger.info("shutdown requested")
        self._shutdown_requested = True

    def _install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._request_shutdown)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._install_signal_handlers(loop)

        worker = await self._authenticate_with_retry()
        logger.info("authenticated as worker %s (%s)", worker.worker_uuid, worker.worker_name)

        last_heartbeat = 0.0
        try:
            while not self._shutdown_requested:
                now = loop.time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    await _heartbeat("available")
                    last_heartbeat = now

                claimed = await _claim()
                if claimed is None:
                    logger.debug("no claimable dispatch item, sleeping %ss", POLL_INTERVAL_SECONDS)
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                dispatch_id, mission_id, _task_id, token, capability_name = claimed
                logger.info("claimed dispatch item %s (mission %s)", dispatch_id, mission_id)
                state = await _execute(dispatch_id, mission_id, token, capability_name)
                logger.info("execution finished for dispatch %s: %s", dispatch_id, state)
                if state == "succeeded":
                    await _try_close_out_mission(mission_id)
        finally:
            await self._shutdown()

    async def _authenticate_with_retry(self, attempts: int = 10, delay_seconds: float = 3.0):
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await _authenticate()
            except AuthorizationDenied as exc:
                last_error = exc
                logger.warning(
                    "worker authentication failed (attempt %s/%s): %s — is the API's startup bootstrap done?",
                    attempt, attempts, exc,
                )
                await asyncio.sleep(delay_seconds)
        raise RuntimeError("Could not authenticate the worker after repeated attempts") from last_error

    async def _shutdown(self) -> None:
        try:
            async with AsyncSessionLocal() as session:
                _, workers, _ = _services(session)
                worker = await workers.authenticate(WORKER_UUID, _credential())
                await workers.shutdown(worker)
            logger.info("worker retired cleanly")
        except Exception as exc:  # best-effort on the way out; never mask the real shutdown
            logger.warning("clean shutdown failed: %s", exc)


async def main() -> None:
    await WorkerProcess().run()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
    sys.exit(0)
