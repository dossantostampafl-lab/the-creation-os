import json

import httpx
import pytest

from app.security_task_force.canonicalize import canonical_hash
from app.security_task_force.event_bus import DEAD_LETTER_SUBJECT, EventBus, IdempotentConsumer, subject_for
from app.security_task_force.events import event
from app.security_task_force.host_capabilities import HostCapabilities
from app.security_task_force.ledger import DispatchLedger
from app.security_task_force.mission_compiler import compile_verified_contract, verify_compiled
from app.security_task_force.range_controller import RangeController, RangeRefused
from app.security_task_force.sandbox import select_sandbox

CANDIDATE = {
    "mission_id": "m1", "creator_id": "c1", "success_criteria": ["evidence"],
    "authorized_targets": ["juice-shop"], "allowed_action_classes": ["validate"], "risk_ceiling": "R2",
}


def test_canonical_hash_ignores_key_order():
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})


def test_compiler_rejects_missing_environment_instead_of_defaulting():
    result = compile_verified_contract(intent="check target", candidate=CANDIDATE, authorized_environments=[])
    assert result.status == "REJECTED" and "environment" in result.reason_codes


def test_compiled_contract_verifies_from_the_persisted_record_only():
    result = compile_verified_contract(intent="validate", candidate=CANDIDATE, authorized_environments=["cyber_range:lab-a"])
    assert result.status == "COMPILED"
    record = result.record()
    assert verify_compiled(record)
    record["contract"]["authorized_targets"] = ["other"]
    assert not verify_compiled(record)


def test_r5_ceiling_is_rejected():
    result = compile_verified_contract(intent="x", candidate={**CANDIDATE, "risk_ceiling": "R5"},
                                       authorized_environments=["cyber_range:lab-a"])
    assert result.status == "REJECTED"


def test_sandbox_never_falls_back_to_plain_docker():
    result = select_sandbox(host=HostCapabilities(docker=True))
    assert result.engine is None and not result.privileged_execution_enabled
    assert select_sandbox(host=HostCapabilities(kata=True, firecracker=True, kvm=True)).engine == "kata"
    assert select_sandbox(host=HostCapabilities(firecracker=True, kvm=True), preferred="kata").engine is None


def test_dispatch_ledger_is_at_most_once(tmp_path):
    ledger = DispatchLedger(tmp_path / "l.json")
    assert ledger.reserve("k") == "reserved"
    assert DispatchLedger(tmp_path / "l.json").reserve("k") == "unknown"  # crash before completion
    ledger.complete("k", {"status": "executed"})
    assert DispatchLedger(tmp_path / "l.json").reserve("k") == "done"


class FakeJetStream:
    def __init__(self):
        self.published = []

    async def publish(self, subject, payload, headers=None):
        self.published.append((subject, payload, headers))


class FakeNats:
    def __init__(self):
        self.js = FakeJetStream()

    def jetstream(self):
        return self.js


async def test_event_bus_uses_event_id_and_consumer_dedupes_and_dead_letters():
    nats = FakeNats()
    bus = EventBus(nats)
    value = event("mission.compiled.v1", "m1", "corr", {"ok": True})
    await bus.publish(value)
    subject, payload, headers = nats.js.published[0]
    assert subject == subject_for("mission.compiled.v1") and headers["Nats-Msg-Id"] == value.event_id
    seen = []

    async def handler(item):
        seen.append(item.event_id)

    consumer = IdempotentConsumer(handler, bus)
    assert await consumer.handle(payload) == "processed"
    assert await consumer.handle(payload) == "duplicate"
    assert await consumer.handle(b"{not an event") == "dead_lettered"
    assert seen == [value.event_id] and nats.js.published[-1][0] == DEAD_LETTER_SUBJECT


def test_unversioned_or_unknown_events_are_rejected():
    with pytest.raises(ValueError):
        event("mission.compiled", "m1", "c", {})
    with pytest.raises(ValueError):
        event("mission.invented.v1", "m1", "c", {})


async def test_range_controller_refuses_real_environments():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"status": "reset", "scenarios": []})

    controller = RangeController(transport=httpx.MockTransport(handler))
    with pytest.raises(RangeRefused):
        await controller.reset("real:prod-a")
    assert calls == []
    assert (await controller.reset("cyber_range:lab-a"))["status"] == "reset"
    assert json.dumps(calls) == '["/reset"]'
