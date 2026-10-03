from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_APP = ROOT / "controller" / "app.py"


def load_controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    scenarios = tmp_path / "catalog.json"
    campaigns = tmp_path / "campaigns.json"
    evidence = tmp_path / "evidence"
    state = tmp_path / "state"
    campaign_state = tmp_path / "campaign-state"
    snapshots = tmp_path / "snapshots"

    def scenario(
        scenario_id: str,
        target: str,
        family: str,
        prerequisites=None,
        purple=False,
        blind=False,
        variants=None,
    ):
        return {
            "id": scenario_id,
            "version": 1,
            "target": target,
            "family": family,
            "difficulty": 2,
            "description": f"{scenario_id} training",
            "objectives": ["produce scoped evidence"],
            "prerequisites": prerequisites or [],
            "success_criteria": ["execution_evidence"],
            "failure_criteria": ["containment_failure"],
            "reset_policy": "deterministic",
            "purple_required": purple,
            "blind": blind,
            "variants": variants or [],
        }

    scenarios.write_text(
        json.dumps({
            "schema_version": 2,
            "environment": "CYBER_RANGE",
            "scenarios": [
                scenario("juice-shop-baseline", "juice-shop", "web_application"),
                scenario("webgoat-baseline", "webgoat", "authorization"),
                scenario("blue-detection-baseline", "juice-shop", "detection",
                         prerequisites=["juice-shop-baseline"], purple=True),
                scenario(
                    "purple-blind-baseline",
                    "juice-shop",
                    "detection",
                    prerequisites=["juice-shop-baseline"],
                    purple=True,
                    blind=True,
                    variants=[
                        {"id": "signal-correlation", "focus": "correlation"},
                        {"id": "evidence-gap", "focus": "evidence_completeness"},
                    ],
                ),
            ],
        }),
        encoding="utf-8",
    )
    campaigns.write_text(
        json.dumps({
            "schema_version": 1,
            "environment": "CYBER_RANGE",
            "campaigns": [{
                "id": "stf-foundation-v1",
                "version": 1,
                "name": "STF Foundation",
                "description": "ordered training",
                "scenario_ids": ["juice-shop-baseline", "webgoat-baseline", "blue-detection-baseline"],
                "completion_policy": "ordered",
                "reset_between_scenarios": True,
                "blind": False,
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("RANGE_SCENARIO_CATALOG", str(scenarios))
    monkeypatch.setenv("RANGE_CAMPAIGN_CATALOG", str(campaigns))
    monkeypatch.setenv("RANGE_EVIDENCE_DIR", str(evidence))
    monkeypatch.setenv("RANGE_STATE_DIR", str(state))
    monkeypatch.setenv("RANGE_CAMPAIGN_STATE_DIR", str(campaign_state))
    monkeypatch.setenv("RANGE_SNAPSHOT_DIR", str(snapshots))

    assert CONTROLLER_APP.exists(), "Range Controller app.py must exist"
    spec = importlib.util.spec_from_file_location("range_controller_under_test", CONTROLLER_APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, evidence, state


def test_controller_lists_only_declared_scenarios(tmp_path, monkeypatch) -> None:
    module, _, _ = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    response = client.get("/scenarios")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["scenarios"]} == {
        "juice-shop-baseline",
        "webgoat-baseline",
        "blue-detection-baseline",
        "purple-blind-baseline",
    }


def test_controller_rejects_unknown_scenario(tmp_path, monkeypatch) -> None:
    module, _, _ = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    response = client.post("/scenarios/not-declared/start")
    assert response.status_code == 404


def test_reset_removes_only_range_state(tmp_path, monkeypatch) -> None:
    module, evidence, state = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    assert client.post("/scenarios/juice-shop-baseline/start").status_code == 200
    assert any(state.iterdir())

    evidence.mkdir(parents=True, exist_ok=True)
    evidence_marker = evidence / "keep.json"
    evidence_marker.write_text("{}", encoding="utf-8")

    response = client.post("/reset")
    assert response.status_code == 200
    assert list(state.iterdir()) == []
    assert evidence_marker.exists(), "reset must not erase audit evidence"


def test_evidence_is_written_only_to_configured_directory(tmp_path, monkeypatch) -> None:
    module, evidence, _ = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    response = client.post(
        "/evidence",
        json={"scenario_id": "juice-shop-baseline", "kind": "verification", "payload": {"ok": True}},
    )
    assert response.status_code == 201
    saved = Path(response.json()["storage_path"])
    assert saved.parent.resolve() == evidence.resolve()
    assert saved.is_file()
    assert os.path.commonpath([saved.resolve(), evidence.resolve()]) == str(evidence.resolve())


def test_save_range_snapshot_and_restore_round_trip(tmp_path, monkeypatch) -> None:
    module, evidence, state = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)

    started = client.post("/scenarios/juice-shop-baseline/start")
    assert started.status_code == 200

    saved = client.post("/snapshots")
    assert saved.status_code == 201
    snapshot_id = saved.json()["snapshot_id"]
    assert saved.json()["state_records"] == 1
    assert any(evidence.iterdir()), "snapshot creation must append audit evidence"

    reset = client.post("/reset")
    assert reset.status_code == 200
    assert list(state.iterdir()) == []

    restored = client.post(f"/snapshots/{snapshot_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["restored_scenarios"] == ["juice-shop-baseline"]

    current = client.get("/state")
    assert current.status_code == 200
    assert [item["scenario_id"] for item in current.json()["scenarios"]] == [
        "juice-shop-baseline"
    ]


def test_snapshot_restore_rejects_unknown_snapshot(tmp_path, monkeypatch) -> None:
    module, _, _ = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    response = client.post("/snapshots/not-present/restore")
    assert response.status_code == 404


def test_reset_preserves_snapshots(tmp_path, monkeypatch) -> None:
    module, _, state = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    assert client.post("/scenarios/webgoat-baseline/start").status_code == 200
    saved = client.post("/snapshots")
    assert saved.status_code == 201
    snapshot_id = saved.json()["snapshot_id"]

    assert client.post("/reset").status_code == 200
    assert list(state.iterdir()) == []

    snapshots = client.get("/snapshots")
    assert snapshots.status_code == 200
    assert snapshot_id in {item["snapshot_id"] for item in snapshots.json()["snapshots"]}


@pytest.mark.parametrize("invalid_state", [[{"scenario_id": "juice-shop-baseline"}, {"scenario_id": "unknown"}], [None], {}, "invalid"])
def test_invalid_snapshot_restore_preserves_existing_state(tmp_path, monkeypatch, invalid_state) -> None:
    module, evidence, state = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    assert client.post("/scenarios/webgoat-baseline/start").status_code == 200
    before = {path.name: path.read_bytes() for path in state.iterdir()}
    saved = client.post("/snapshots").json()
    snapshot_id = saved["snapshot_id"]
    snapshot = module.SNAPSHOT_DIR / f"{snapshot_id}.json"
    record = json.loads(snapshot.read_text())
    record["state"] = invalid_state
    snapshot.write_text(json.dumps(record))
    audit_before = {path.name for path in evidence.iterdir()}

    response = client.post(f"/snapshots/{snapshot_id}/restore")

    assert response.status_code == 409
    assert {path.name: path.read_bytes() for path in state.iterdir()} == before
    assert {path.name for path in evidence.iterdir()} == audit_before


def test_campaign_runs_declared_scenarios_in_order_with_deterministic_reset(tmp_path, monkeypatch) -> None:
    module, evidence, state = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)

    started = client.post("/campaigns/stf-foundation-v1/start")
    assert started.status_code == 200
    assert started.json()["current_scenario_id"] == "juice-shop-baseline"
    assert [item["scenario_id"] for item in client.get("/state").json()["scenarios"]] == ["juice-shop-baseline"]

    second = client.post("/campaigns/stf-foundation-v1/advance")
    assert second.status_code == 200
    assert second.json()["current_scenario_id"] == "webgoat-baseline"
    assert second.json()["completed_scenarios"] == ["juice-shop-baseline"]
    assert [item["scenario_id"] for item in client.get("/state").json()["scenarios"]] == ["webgoat-baseline"]

    third = client.post("/campaigns/stf-foundation-v1/advance")
    assert third.json()["current_scenario_id"] == "blue-detection-baseline"
    finished = client.post("/campaigns/stf-foundation-v1/advance")
    assert finished.json()["status"] == "completed"
    assert finished.json()["current_scenario_id"] is None
    assert list(state.glob("*.json")) == []
    assert any(evidence.iterdir()), "campaign transitions must append audit evidence"


def test_snapshot_round_trip_preserves_campaign_progress(tmp_path, monkeypatch) -> None:
    module, _, _ = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)
    assert client.post("/campaigns/stf-foundation-v1/start").status_code == 200
    assert client.post("/campaigns/stf-foundation-v1/advance").json()["current_scenario_id"] == "webgoat-baseline"

    snapshot_id = client.post("/snapshots").json()["snapshot_id"]
    assert client.post("/reset").status_code == 200
    assert client.get("/campaigns/stf-foundation-v1/state").status_code == 404

    restored = client.post(f"/snapshots/{snapshot_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["restored_campaigns"] == ["stf-foundation-v1"]
    current = client.get("/campaigns/stf-foundation-v1/state").json()
    assert current["current_scenario_id"] == "webgoat-baseline"
    assert current["completed_scenarios"] == ["juice-shop-baseline"]


def test_blind_scenario_commits_variant_without_disclosing_it_and_snapshot_preserves_it(tmp_path, monkeypatch) -> None:
    module, _, state = load_controller(tmp_path, monkeypatch)
    client = TestClient(module.app)

    catalog = client.get("/scenarios").json()["scenarios"]
    blind = next(item for item in catalog if item["id"] == "purple-blind-baseline")
    assert blind["blind"] is True
    assert blind["variant_count"] == 2
    assert "variants" not in blind

    started = client.post("/scenarios/purple-blind-baseline/start")
    assert started.status_code == 200
    public = started.json()
    assert "variant_id" not in public and "variant_nonce" not in public
    assert len(public["variant_commitment"]) == 64

    raw = json.loads((state / "purple-blind-baseline.json").read_text(encoding="utf-8"))
    assert raw["variant_id"] in {"signal-correlation", "evidence-gap"}
    assert raw["variant_nonce"]
    assert raw["variant_commitment"] == public["variant_commitment"]

    snapshot_id = client.post("/snapshots").json()["snapshot_id"]
    assert client.post("/reset").status_code == 200
    assert client.post(f"/snapshots/{snapshot_id}/restore").status_code == 200
    restored_raw = json.loads((state / "purple-blind-baseline.json").read_text(encoding="utf-8"))
    assert restored_raw["variant_id"] == raw["variant_id"]
    assert restored_raw["variant_nonce"] == raw["variant_nonce"]
    visible = client.get("/state").json()["scenarios"][0]
    assert "variant_id" not in visible and visible["variant_commitment"] == raw["variant_commitment"]
