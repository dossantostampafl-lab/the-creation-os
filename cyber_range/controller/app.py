from __future__ import annotations

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
CATALOG_PATH = Path(os.environ.get("RANGE_SCENARIO_CATALOG", "/app/scenarios/catalog.json"))
EVIDENCE_DIR = Path(os.environ.get("RANGE_EVIDENCE_DIR", "/evidence"))
STATE_DIR = Path(os.environ.get("RANGE_STATE_DIR", "/state"))

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)


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


app = FastAPI(title="Creation Cyber Range Controller", version="1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": "CYBER_RANGE"}


@app.get("/scenarios")
def list_scenarios() -> dict[str, list[dict[str, Any]]]:
    return {"scenarios": _load_catalog()}


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
