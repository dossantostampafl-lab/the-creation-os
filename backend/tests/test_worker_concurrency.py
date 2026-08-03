"""Lote: P4/P5 — concorrência real de worker (lease reclaim e retry/backoff).

Everything here spawns real `python -m app.worker` OS processes against the
real test database — no mocking of leasing, reclaim, or backoff timing.
Reclaim and retry/backoff logic itself was already proven correct in a
single process (test_dispatch_error_paths_expiration_acknowledge_and_release,
DispatchService.fail()'s tests) — this file's only job is to prove that same
logic survives real process death and real wall-clock waits, not to
re-derive it.

Slow by nature (subprocess start-up + real lease/backoff waits measured in
seconds, not mocked) — marked `concurrency` in addition to `integration` so
an operator can exclude these specifically with `-m "not concurrency"`
without changing what the rest of the suite's default run covers. See
ARCHITECTURE.md.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from db_safety import create_isolated_test_engine, validated_test_database_url
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.dispatch_state_machine import retry_delay
from app.models.dispatch import DispatchAttempt, DispatchItem
from app.models.entities import Agent, Capability, Chronicle, Conversation, Creator, Inception, Message, Mission, Task
from app.models.execution import AgentExecution, AgentExecutionEvent
from app.repositories.dispatch import DispatchRepository
from app.repositories.tree_core import TreeCoreRepository
from app.repositories.workers import WorkerRepository
from app.services.dispatch import DispatchService
from app.services.tree_core import TreeCoreService
from app.services.workers import WorkerService

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def _reset_dispatch_queue(factory) -> None:
    """Both P4 and P5 need a dispatch_items queue containing only the one
    item they themselves seed. Found the hard way: leftover queued items
    from an earlier run of this same file (which deliberately doesn't
    TRUNCATE the other tables — see _seed_dispatch_item) are real,
    matching-capability targets a freshly-spawned worker will race for,
    non-deterministically stealing the claim meant for a specific worker in
    the test and making the whole scenario unreproducible. dispatch_items
    and dispatch_attempts aren't part of the migration-seeded tables any
    other test depends on existing, so truncating them here is safe."""
    async with factory() as session:
        await session.execute(text("TRUNCATE dispatch_items, dispatch_attempts RESTART IDENTITY CASCADE"))
        await session.commit()


async def _seed_dispatch_item(factory, capability_name: str, max_attempts: int) -> dict:
    """Builds one real, enqueued DispatchItem end-to-end through the public
    services (Creator -> Conversation -> Message -> Inception -> Mission ->
    Task -> DispatchService.enqueue), the same shape test_dispatch_integration.py's
    dispatch_db fixture already proves works — minus the TRUNCATE, since this
    file's tests run 5x in a row against a shared, non-isolated database and
    must not stomp on each other or on unrelated tests sharing it. Every id
    is fresh per call; the capability is get-or-create by name since
    `capabilities.name` is UNIQUE (see ARCHITECTURE.md, Lote: corrigir bug de
    migration 0023, on why an unqualified re-insert under a colliding name is
    a real footgun here)."""
    ids = {key: str(uuid.uuid4()) for key in ("conversation", "message", "inception", "mission", "agent", "task")}
    async with factory() as session:
        # `creator` enforces a real singleton constraint (uq_creator_singleton,
        # migration 0024) — at most one row, ever. Reuse whatever creator
        # already exists in this database rather than inserting a fresh one,
        # since this fixture deliberately doesn't TRUNCATE (see docstring).
        creator = await session.scalar(select(Creator))
        if creator is None:
            creator = Creator(id=str(uuid.uuid4()), username=f"creator-{uuid.uuid4().hex[:8]}", password_hash="unused", is_active=True)
            session.add(creator)
            await session.commit()
        ids["creator"] = creator.id
        session.add(Conversation(id=ids["conversation"], creator_id=ids["creator"], title="concurrency", status="active"))
        await session.commit()
        session.add(
            Message(
                id=ids["message"], conversation_id=ids["conversation"], role="creator", actor_id=ids["creator"],
                correlation_id=str(uuid.uuid4()), content="x", route="central", metadata_json={},
            )
        )
        await session.commit()
        session.add(
            Inception(
                id=ids["inception"], conversation_id=ids["conversation"], source_message_id=ids["message"],
                title="i", description="d", status="approved", trinity_assessment_json={},
            )
        )
        await session.commit()
        session.add(
            Mission(
                id=ids["mission"], inception_id=ids["inception"], creator_id=ids["creator"],
                title="m", objective="o", status="authorized", authorization_json={},
            )
        )
        await session.commit()

        capability = await session.scalar(select(Capability).where(Capability.name == capability_name))
        if capability is None:
            capability = Capability(id=str(uuid.uuid4()), name=capability_name, description="concurrency test capability")
            session.add(capability)
            await session.commit()
        ids["capability"] = capability.id

        agent = Agent(
            id=ids["agent"], name=f"agent-{ids['agent'][:8]}", description="", universe_name="central",
            priority=10, status="idle", version=1, heartbeat_at=datetime.now(timezone.utc),
            enabled=True, active=True, capabilities_json={},
        )
        agent.capabilities = [capability]
        session.add(agent)
        await session.commit()

        session.add(
            Task(
                id=ids["task"], mission_id=ids["mission"], name="t", description="d",
                required_capability_id=ids["capability"], priority=1, state="ready",
                retry_limit=3, retry_count=0, timeout_seconds=30, status="PENDING",
                input_json={}, output_json={}, error_json={}, attempt_count=0,
                max_attempts=max_attempts, idempotency_key=str(uuid.uuid4()),
            )
        )
        await session.commit()

    async with factory() as session:
        dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        item = await dispatch.enqueue(ids["creator"], ids["task"], 0, max_attempts)
        ids["dispatch_item"] = item.id
    return ids


async def _register_worker(factory, name: str, capability_names: list[str]) -> tuple[str, str]:
    worker_uuid = str(uuid.uuid4())
    async with factory() as session:
        dispatch = DispatchService(DispatchRepository(session), TreeCoreService(TreeCoreRepository(session)))
        workers = WorkerService(WorkerRepository(session), dispatch)
        _, token = await workers.register(worker_uuid, name, "1.0", capability_names)
    return worker_uuid, token


async def _poll(factory, query_fn, timeout: float, interval: float = 0.3, description: str = ""):
    deadline = time.monotonic() + timeout
    while True:
        async with factory() as session:
            result = await query_fn(session)
        if result is not None:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out after {timeout}s waiting for: {description}")
        await asyncio.sleep(interval)


def _worker_env(worker_uuid: str, credential: str, database_url: str, **overrides) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "test",
            "APP_SECRET_KEY": "test-secret-key-at-least-32-characters",
            "CREATOR_BOOTSTRAP_USERNAME": "creator",
            "CREATOR_BOOTSTRAP_PASSWORD": "test-password",
            "REDIS_URL": "redis://localhost:6379/0",
            "DATABASE_URL": database_url,
            "WORKER_UUID": worker_uuid,
            "WORKER_CREDENTIAL_OVERRIDE": credential,
            # Empirically required on this Windows/asyncio ProactorEventLoop
            # host: a worker process that goes many cycles without any
            # stdout/logging activity (the normal "nothing claimable yet"
            # case) can stall indefinitely mid-poll — confirmed by direct
            # reproduction outside pytest entirely (plain foreground process,
            # no test harness involved). Turning on the per-cycle DEBUG log
            # app/worker.py's run() loop already emits reliably prevents it.
            # Not observed as a concern on the production Linux/Docker
            # target (different event loop backend); see ARCHITECTURE.md,
            # Lote: P4/P5 — concorrência real de worker.
            "LOG_LEVEL": "DEBUG",
        }
    )
    for key, value in overrides.items():
        env[key] = str(value)
    return env


@pytest.fixture
def spawned_workers(tmp_path):
    """Guarantees every real `python -m app.worker` process a test in this
    file starts is force-killed and reaped in teardown, even if the test
    body raises partway through — real subprocesses left running would
    otherwise hang around as orphans (see section 4 of the lote prompt)."""
    processes: list[tuple[str, subprocess.Popen, object]] = []

    def spawn(label: str, worker_uuid: str, credential: str, database_url: str, **overrides) -> subprocess.Popen:
        log_path = tmp_path / f"{label}.log"
        log_file = open(log_path, "w", encoding="utf-8")
        env = _worker_env(worker_uuid, credential, database_url, **overrides)
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.worker"],
            cwd=str(_BACKEND_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        processes.append((label, proc, log_file))
        return proc

    yield spawn

    failures = []
    for label, proc, log_file in processes:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            failures.append(label)
        log_file.close()
    if failures:
        pytest.fail(f"worker process(es) {failures} did not exit within 10s of being killed — possible orphan")


@pytest.mark.asyncio
async def test_p4_lease_reclaim_two_real_worker_processes(spawned_workers):
    """P4: worker A claims a real task, is killed without a chance to
    release (no SIGTERM, no graceful shutdown — proc.kill()), and worker B
    — a second, independently-registered, genuinely concurrent real OS
    process — reclaims and completes it once (and only once) A's real
    lease_expires_at has actually passed."""
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    database_url = validated_test_database_url()
    lease_seconds = 10

    try:
        await _reset_dispatch_queue(factory)
        ids = await _seed_dispatch_item(factory, "concurrency_test", max_attempts=3)
        worker_a_uuid, worker_a_token = await _register_worker(factory, "test-worker-p4-a", ["concurrency_test"])
        worker_b_uuid, worker_b_token = await _register_worker(factory, "test-worker-p4-b", ["concurrency_test"])

        # Worker B is deliberately not started yet: spawning both at once
        # would race them for who claims *first*, which isn't what this
        # test proves. B only starts once A is confirmed to hold the lease
        # and has been killed — so any claim B makes can only be a genuine
        # reclaim of A's abandoned lease, never a race for the first claim.
        #
        # capability="concurrency_test" (not "planning"): structured_echo
        # completes a full claim-to-acknowledge cycle in well under 150ms
        # locally — faster than any practical poll interval can reliably
        # observe the item mid-flight (state=="leased") before it's already
        # done. concurrency_test_echo is the same kind of trivial handler,
        # gated to add a real, observable delay only when this env var is
        # set (default 0 — no effect on any real deployment); see
        # app/agents/handlers.py and ARCHITECTURE.md.
        #
        # 6s, not a smaller value: a real (if infrequent) flake was observed
        # at 3s — under a scheduling stall on the test's own poll loop, A's
        # near-instant claim->create->accept->started->(sleep)->succeeded
        # chain could complete before the test's kill actually landed. 6s
        # gives real margin over ordinary scheduling jitter without making
        # the test needlessly slow.
        handler_delay_seconds = 6
        proc_a = spawned_workers(
            "p4-a", worker_a_uuid, worker_a_token, database_url,
            WORKER_LEASE_SECONDS=lease_seconds, CONCURRENCY_TEST_HANDLER_DELAY_SECONDS=handler_delay_seconds,
        )

        async def leased_by_a(session):
            item = await session.get(DispatchItem, ids["dispatch_item"])
            return item if item and item.state == "leased" and item.lease_owner == worker_a_uuid else None

        await _poll(factory, leased_by_a, timeout=20, description="worker A to claim the dispatch item")

        # Deliberately don't kill A the instant "leased" is observed: that
        # dispatch-level state is set by workers.claim() *before*
        # execution_service.create() even runs, milliseconds ahead of it —
        # killing here often caught A before its AgentExecution row was even
        # committed, so there was nothing orphaned to reclaim at the
        # execution level (confirmed by direct inspection: a killed-this-
        # early A leaves zero agent_executions rows, and B's create() then
        # just inserts fresh — correct dispatch-level reclaim, but not the
        # execution-row-collision scenario this event_type exists for).
        # Wait for the execution row to actually exist first, so the kill
        # reliably lands in the window this test is about: after create()
        # committed, before acknowledge()/fail().
        async def execution_row_exists(session):
            return await session.scalar(
                select(AgentExecution).where(AgentExecution.dispatch_item_id == ids["dispatch_item"])
            )

        await _poll(factory, execution_row_exists, timeout=20, description="worker A's execution row to be committed")

        async with factory() as session:
            leased_item = await session.get(DispatchItem, ids["dispatch_item"])
        original_lease_expires_at = leased_item.lease_expires_at

        # Simulate a crashed/hung worker: no SIGTERM, no graceful release.
        # subprocess.Popen.kill() is TerminateProcess on Windows / SIGKILL on
        # POSIX — either way, the process gets no chance to run its own
        # shutdown handler.
        proc_a.kill()
        proc_a.wait(timeout=10)

        spawned_workers("p4-b", worker_b_uuid, worker_b_token, database_url, WORKER_LEASE_SECONDS=lease_seconds)

        async def acknowledged_by_b(session):
            item = await session.get(DispatchItem, ids["dispatch_item"])
            return item if item and item.state == "acknowledged" and item.lease_owner == worker_b_uuid else None

        wait_budget = lease_seconds + 15  # real lease expiry + poll interval + execution margin
        reclaimed_item = await _poll(
            factory, acknowledged_by_b, timeout=wait_budget, description="worker B to reclaim and complete the task"
        )
        assert reclaimed_item.attempt_count == 0  # never failed — the first claim just expired, it wasn't a failed attempt

        async with factory() as session:
            attempts = list(
                (
                    await session.scalars(
                        select(DispatchAttempt)
                        .where(DispatchAttempt.dispatch_item_id == ids["dispatch_item"])
                        .order_by(DispatchAttempt.created_at)
                    )
                ).all()
            )
        leased_events = [a for a in attempts if a.event_type == "leased"]
        assert [a.worker_id for a in leased_events] == [worker_a_uuid, worker_b_uuid], (
            f"expected exactly A then B to lease this item, got {[a.worker_id for a in leased_events]}"
        )
        # Real reclaim, not a premature grab: B's lease could not have
        # happened before A's real lease_expires_at actually passed.
        b_leased_at = leased_events[1].created_at
        assert b_leased_at >= original_lease_expires_at, (
            f"worker B leased at {b_leased_at}, before A's real lease_expires_at {original_lease_expires_at} — reclaim happened too early"
        )

        # Lote: event_type dedicado para reclaim de lease. A's execution_created
        # (from its own killed-mid-flight attempt) and B's resume of that same
        # row must be distinguishable — B's resume records "execution_reclaimed",
        # not another "execution_created".
        async with factory() as session:
            execution = await session.scalar(
                select(AgentExecution).where(AgentExecution.dispatch_item_id == ids["dispatch_item"])
            )
            assert execution is not None
            execution_events = list(
                (
                    await session.scalars(
                        select(AgentExecutionEvent)
                        .where(AgentExecutionEvent.execution_id == execution.id)
                        .order_by(AgentExecutionEvent.sequence)
                    )
                ).all()
            )
        # Not asserted as one fixed literal sequence: real wall-clock timing
        # decides how far A's own process gets (create only? create+accept?
        # create+accept+started, mid-handler-sleep?) before the kill signal
        # actually lands — any of those are legitimate. What must hold
        # regardless: exactly one execution_created (A's original attempt,
        # never duplicated), exactly one execution_reclaimed (B's resume,
        # strictly after it), and the execution eventually reaches a real
        # terminal success.
        event_types = [e.event_type for e in execution_events]
        assert event_types.count("execution_created") == 1, event_types
        assert event_types.count("execution_reclaimed") == 1, event_types
        assert event_types[0] == "execution_created", event_types
        assert event_types.index("execution_reclaimed") > event_types.index("execution_created"), event_types
        assert "execution_succeeded" in event_types, event_types
        assert event_types[-1] == "result_returned", event_types
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_p5_retry_backoff_real_worker_process(spawned_workers):
    """P5: a real worker process attempts a task whose capability has no
    registered handler (deterministic, guaranteed failure every attempt —
    the simplest reversible way to get "fails until max_attempts", per
    section 6 of the lote prompt), and the real elapsed time between
    attempts is measured against DispatchService's real retry_delay()
    formula — not presumed, not mocked."""
    engine = create_isolated_test_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    database_url = validated_test_database_url()
    retry_base = 2
    retry_maximum = 10
    max_attempts = 2
    flaky_capability = f"flaky_test_{uuid.uuid4().hex[:8]}"

    try:
        await _reset_dispatch_queue(factory)
        ids = await _seed_dispatch_item(factory, flaky_capability, max_attempts=max_attempts)
        worker_uuid, token = await _register_worker(factory, "test-worker-p5", [flaky_capability])

        spawned_workers(
            "p5", worker_uuid, token, database_url,
            DISPATCH_RETRY_BASE_SECONDS=retry_base, DISPATCH_RETRY_MAXIMUM_SECONDS=retry_maximum,
        )

        async def first_retry_scheduled(session):
            item = await session.get(DispatchItem, ids["dispatch_item"])
            return item if item and item.state == "retry_scheduled" and item.attempt_count == 1 else None

        await _poll(factory, first_retry_scheduled, timeout=20, description="first attempt to fail into retry_scheduled")
        t1 = time.monotonic()

        async def dead_lettered(session):
            item = await session.get(DispatchItem, ids["dispatch_item"])
            return item if item and item.state == "dead_lettered" and item.attempt_count == max_attempts else None

        await _poll(
            factory, dead_lettered, timeout=retry_base + retry_maximum + 15, description="second attempt to dead-letter"
        )
        t2 = time.monotonic()

        observed_delay = t2 - t1
        expected_delay = retry_delay(retry_base, 1, retry_maximum)
        # Real measured wait, not presumed: must be at least roughly the
        # scheduled delay (small slack for polling/clock granularity), and
        # not implausibly longer either — proves the worker actually waited
        # for available_at rather than either ignoring it or hanging.
        assert observed_delay >= expected_delay - 1.0, f"backoff was shorter than scheduled: {observed_delay:.2f}s < {expected_delay}s"
        assert observed_delay < expected_delay + 10.0, f"backoff took implausibly long: {observed_delay:.2f}s"

        async def mission_failed_event(session):
            return await session.scalar(
                select(Chronicle).where(Chronicle.aggregate_id == ids["mission"], Chronicle.event_type == "mission_failed")
            )

        event = await _poll(factory, mission_failed_event, timeout=10, description="mission_failed Chronicle event")
        assert event is not None

        async with factory() as session:
            attempts = list(
                (
                    await session.scalars(
                        select(DispatchAttempt)
                        .where(DispatchAttempt.dispatch_item_id == ids["dispatch_item"])
                        .order_by(DispatchAttempt.created_at)
                    )
                ).all()
            )
        event_sequence = [a.event_type for a in attempts if a.event_type in {"retry_scheduled", "dead_lettered"}]
        assert event_sequence == ["retry_scheduled", "dead_lettered"]
    finally:
        await engine.dispose()
