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
    evidence = tmp_path / "evidence"
    state = tmp_path / "state"
    scenarios.write_text(
        json.dumps(
            {
                "scenarios": [
                    {"id": "juice-shop-baseline", "target": "juice-shop"},
                    {"id": "webgoat-baseline", "target": "webgoat"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RANGE_SCENARIO_CATALOG", str(scenarios))
    monkeypatch.setenv("RANGE_EVIDENCE_DIR", str(evidence))
    monkeypatch.setenv("RANGE_STATE_DIR", str(state))

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
