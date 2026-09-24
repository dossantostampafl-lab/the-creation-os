import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field


SCENARIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CATALOG_PATH = Path(os.environ.get("RANGE_SCENARIO_CATALOG", "/app/scenarios/catalog.json"))
EVIDENCE_DIR = Path(os.environ.get("RANGE_EVIDENCE_DIR", "/evidence"))
STATE_DIR = Path(os.environ.get("RANGE_STATE_DIR", "/state"))
SNAPSHOT_DIR = Path(os.environ.get("RANGE_SNAPSHOT_DIR", "/snapshots"))

for directory in (EVIDENCE_DIR, STATE_DIR, SNAPSHOT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


class EvidenceRequest(BaseModel):
    scenario_id: str
    kind: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]


def _load_catalog() -> list[dict[str, Any]]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    scenarios = data.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise RuntimeError("scenario catalog must contain a scenarios list")
    for item in scenarios:
        scenario_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(scenario_id, str) or not SCENARIO_ID.fullmatch(scenario_id):
            raise RuntimeError("scenario catalog contains an invalid id")
    return scenarios


def _scenario(scenario_id: str) -> dict[str, Any]:
    if not SCENARIO_ID.fullmatch(scenario_id):
        raise HTTPException(status_code=404, detail="scenario not declared")
    for item in _load_catalog():
        if item["id"] == scenario_id:
            return item
    raise HTTPException(status_code=404, detail="scenario not declared")


def _state_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(STATE_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = record.get("scenario_id")
        if isinstance(scenario_id, str) and SCENARIO_ID.fullmatch(scenario_id):
            records.append(record)
    return records


def _write_audit_record(kind: str, payload: dict[str, Any]) -> str:
    evidence_id = str(uuid4())
    record = {
        "evidence_id": evidence_id,
        "scenario_id": payload.get("scenario_id", "range"),
        "kind": kind,
        "payload": payload,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    (EVIDENCE_DIR / f"{evidence_id}.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8"
    )
    return evidence_id


app = FastAPI(title="Creation Cyber Range Controller", version="1.1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": "CYBER_RANGE"}


@app.get("/scenarios")
def list_scenarios() -> dict[str, list[dict[str, Any]]]:
    return {"scenarios": _load_catalog()}


@app.get("/state")
def get_range_state() -> dict[str, Any]:
    return {"environment": "CYBER_RANGE", "scenarios": _state_records()}


@app.post("/scenarios/{scenario_id}/start")
def start_scenario(scenario_id: str) -> dict[str, Any]:
    scenario = _scenario(scenario_id)
    record = {
        "scenario_id": scenario_id,
        "target": scenario.get("target"),
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (STATE_DIR / f"{scenario_id}.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8"
    )
    return record


@app.post("/reset")
def reset_range_state() -> dict[str, Any]:
    removed = 0
    for path in STATE_DIR.iterdir():
        if path.is_file():
            path.unlink()
            removed += 1
    return {"status": "reset", "removed_state_files": removed}


@app.post("/snapshots", status_code=status.HTTP_201_CREATED)
def save_range() -> dict[str, Any]:
    snapshot_id = f"range-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    record = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "environment": "CYBER_RANGE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "state": _state_records(),
    }
    destination = SNAPSHOT_DIR / f"{snapshot_id}.json"
    destination.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    evidence_id = _write_audit_record(
        "range_snapshot_saved",
        {"snapshot_id": snapshot_id, "state_records": len(record["state"])},
    )
    return {
        "snapshot_id": snapshot_id,
        "state_records": len(record["state"]),
        "evidence_id": evidence_id,
    }


@app.get("/snapshots")
def list_range_snapshots() -> dict[str, Any]:
    snapshots = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        snapshots.append(
            {
                "snapshot_id": record.get("snapshot_id"),
                "created_at": record.get("created_at"),
                "state_records": len(record.get("state", [])),
            }
        )
    return {"snapshots": snapshots}


@app.post("/snapshots/{snapshot_id}/restore")
def restore_range(snapshot_id: str) -> dict[str, Any]:
    if not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise HTTPException(status_code=404, detail="snapshot not found")
    source = SNAPSHOT_DIR / f"{snapshot_id}.json"
    if not source.is_file():
        raise HTTPException(status_code=404, detail="snapshot not found")
    record = json.loads(source.read_text(encoding="utf-8"))
    if record.get("environment") != "CYBER_RANGE" or record.get("snapshot_id") != snapshot_id:
        raise HTTPException(status_code=409, detail="invalid cyber range snapshot")

    restored_ids: list[str] = []
    for path in STATE_DIR.glob("*.json"):
        path.unlink()
    for state_record in record.get("state", []):
        scenario_id = state_record.get("scenario_id")
        if not isinstance(scenario_id, str):
            raise HTTPException(status_code=409, detail="invalid snapshot state")
        _scenario(scenario_id)
        (STATE_DIR / f"{scenario_id}.json").write_text(
            json.dumps(state_record, sort_keys=True), encoding="utf-8"
        )
        restored_ids.append(scenario_id)

    evidence_id = _write_audit_record(
        "range_snapshot_restored",
        {"snapshot_id": snapshot_id, "scenario_ids": restored_ids},
    )
    return {
        "snapshot_id": snapshot_id,
        "restored_scenarios": restored_ids,
        "evidence_id": evidence_id,
    }


@app.post("/evidence", status_code=status.HTTP_201_CREATED)
def write_evidence(request: EvidenceRequest) -> dict[str, Any]:
    _scenario(request.scenario_id)
    evidence_id = str(uuid4())
    record = {
        "evidence_id": evidence_id,
        "scenario_id": request.scenario_id,
        "kind": request.kind,
        "payload": request.payload,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = EVIDENCE_DIR / f"{evidence_id}.json"
    destination.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return {
        "evidence_id": evidence_id,
        "storage_path": str(destination),
        "scenario_id": request.scenario_id,
    }
