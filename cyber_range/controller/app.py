import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

SCENARIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SCENARIO_FAMILIES = {"web_application", "authorization", "detection"}
CATALOG_PATH = Path(os.environ.get("RANGE_SCENARIO_CATALOG", "/app/scenarios/catalog.json"))
CAMPAIGN_CATALOG_PATH = Path(os.environ.get("RANGE_CAMPAIGN_CATALOG", "/app/scenarios/campaigns.json"))
EVIDENCE_DIR = Path(os.environ.get("RANGE_EVIDENCE_DIR", "/evidence"))
STATE_DIR = Path(os.environ.get("RANGE_STATE_DIR", "/state"))
CAMPAIGN_STATE_DIR = Path(os.environ.get("RANGE_CAMPAIGN_STATE_DIR", "/campaign-state"))
SNAPSHOT_DIR = Path(os.environ.get("RANGE_SNAPSHOT_DIR", "/snapshots"))

for directory in (EVIDENCE_DIR, STATE_DIR, CAMPAIGN_STATE_DIR, SNAPSHOT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


class EvidenceRequest(BaseModel):
    scenario_id: str
    kind: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]


def _valid_string_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item.strip()) and len(item) <= 256 for item in value)
    )


def _load_catalog() -> list[dict[str, Any]]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 2 or data.get("environment") not in (None, "CYBER_RANGE"):
        raise RuntimeError("scenario catalog schema is not supported")
    scenarios = data.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise RuntimeError("scenario catalog must contain a scenarios list")
    ids: set[str] = set()
    for item in scenarios:
        if not isinstance(item, dict):
            raise RuntimeError("scenario catalog contains an invalid record")
        scenario_id = item.get("id")
        if not isinstance(scenario_id, str) or not SCENARIO_ID.fullmatch(scenario_id) or scenario_id in ids:
            raise RuntimeError("scenario catalog contains an invalid or duplicate id")
        ids.add(scenario_id)
        if not isinstance(item.get("version"), int) or int(item["version"]) < 1:
            raise RuntimeError("scenario manifest version must be a positive integer")
        if not isinstance(item.get("target"), str) or not item["target"]:
            raise RuntimeError("scenario manifest target is required")
        if item.get("family") not in SCENARIO_FAMILIES:
            raise RuntimeError("scenario manifest family is not supported")
        if not isinstance(item.get("difficulty"), int) or not 1 <= int(item["difficulty"]) <= 5:
            raise RuntimeError("scenario manifest difficulty must be between 1 and 5")
        if not _valid_string_list(item.get("objectives"), allow_empty=False):
            raise RuntimeError("scenario manifest objectives are required")
        if not _valid_string_list(item.get("prerequisites", [])):
            raise RuntimeError("scenario manifest prerequisites are invalid")
        if not _valid_string_list(item.get("success_criteria"), allow_empty=False):
            raise RuntimeError("scenario manifest success criteria are required")
        if not _valid_string_list(item.get("failure_criteria"), allow_empty=False):
            raise RuntimeError("scenario manifest failure criteria are required")
        if item.get("reset_policy") != "deterministic":
            raise RuntimeError("scenario manifest must declare deterministic reset")
        if not isinstance(item.get("purple_required"), bool) or not isinstance(item.get("blind"), bool):
            raise RuntimeError("scenario manifest flags are invalid")
        variants = item.get("variants", [])
        if not isinstance(variants, list):
            raise RuntimeError("scenario variants must be a list")
        variant_ids: set[str] = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise RuntimeError("scenario contains an invalid variant")
            variant_id = variant.get("id")
            if (
                not isinstance(variant_id, str)
                or not SCENARIO_ID.fullmatch(variant_id)
                or variant_id in variant_ids
                or not isinstance(variant.get("focus"), str)
                or not variant["focus"]
            ):
                raise RuntimeError("scenario contains an invalid variant")
            variant_ids.add(variant_id)
        if item.get("blind") and len(variants) < 2:
            raise RuntimeError("blind scenarios require at least two hidden variants")
    for item in scenarios:
        prerequisites = set(item.get("prerequisites", []))
        if not prerequisites.issubset(ids) or item["id"] in prerequisites:
            raise RuntimeError("scenario manifest prerequisites are not declared")
    return scenarios


def _scenario(scenario_id: str) -> dict[str, Any]:
    if not SCENARIO_ID.fullmatch(scenario_id):
        raise HTTPException(status_code=404, detail="scenario not declared")
    for item in _load_catalog():
        if item["id"] == scenario_id:
            return item
    raise HTTPException(status_code=404, detail="scenario not declared")


def _load_campaigns() -> list[dict[str, Any]]:
    data = json.loads(CAMPAIGN_CATALOG_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("environment") not in (None, "CYBER_RANGE"):
        raise RuntimeError("campaign catalog schema is not supported")
    campaigns = data.get("campaigns", [])
    if not isinstance(campaigns, list):
        raise RuntimeError("campaign catalog must contain a campaigns list")
    scenario_ids = {item["id"] for item in _load_catalog()}
    seen: set[str] = set()
    for item in campaigns:
        if not isinstance(item, dict):
            raise RuntimeError("campaign catalog contains an invalid record")
        campaign_id = item.get("id")
        if not isinstance(campaign_id, str) or not SCENARIO_ID.fullmatch(campaign_id) or campaign_id in seen:
            raise RuntimeError("campaign catalog contains an invalid or duplicate id")
        seen.add(campaign_id)
        if not isinstance(item.get("version"), int) or int(item["version"]) < 1:
            raise RuntimeError("campaign version must be a positive integer")
        ordered = item.get("scenario_ids")
        if not _valid_string_list(ordered, allow_empty=False) or not set(ordered).issubset(scenario_ids):
            raise RuntimeError("campaign contains an undeclared scenario")
        if len(set(ordered)) != len(ordered):
            raise RuntimeError("campaign scenario ids must be unique")
        if item.get("completion_policy") != "ordered":
            raise RuntimeError("only ordered campaigns are supported")
        if not isinstance(item.get("reset_between_scenarios"), bool) or not isinstance(item.get("blind"), bool):
            raise RuntimeError("campaign flags are invalid")
        completed: set[str] = set()
        by_id = {scenario["id"]: scenario for scenario in _load_catalog()}
        for scenario_id in ordered:
            if not set(by_id[scenario_id].get("prerequisites", [])).issubset(completed):
                raise RuntimeError("campaign order does not satisfy scenario prerequisites")
            completed.add(scenario_id)
    return campaigns


def _campaign(campaign_id: str) -> dict[str, Any]:
    if not SCENARIO_ID.fullmatch(campaign_id):
        raise HTTPException(status_code=404, detail="campaign not declared")
    for item in _load_campaigns():
        if item["id"] == campaign_id:
            return item
    raise HTTPException(status_code=404, detail="campaign not declared")


def _safe_child(base: Path, filename: str) -> Path:
    candidate = (base / filename).resolve()
    root = base.resolve()
    if candidate.parent != root:
        raise RuntimeError("path escapes cyber range storage root")
    return candidate


def _validated_name(name: str, pattern: re.Pattern[str]) -> str:
    if not pattern.fullmatch(name):
        raise RuntimeError("cyber range identifier is not allowed")
    return name


def _declared_id(scenario: dict[str, Any]) -> str:
    return _validated_name(str(scenario["id"]), SCENARIO_ID)


def _public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    visible = dict(scenario)
    if visible.get("blind"):
        variants = visible.pop("variants", [])
        visible["variant_count"] = len(variants)
    return visible


def _public_state(record: dict[str, Any]) -> dict[str, Any]:
    visible = dict(record)
    if visible.get("blind"):
        visible.pop("variant_id", None)
        visible.pop("variant_nonce", None)
    return visible


def _state_records(*, public: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(STATE_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = record.get("scenario_id")
        if isinstance(scenario_id, str) and SCENARIO_ID.fullmatch(scenario_id):
            records.append(_public_state(record) if public else record)
    return records


def _campaign_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(CAMPAIGN_STATE_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        campaign_id = record.get("campaign_id")
        if isinstance(campaign_id, str) and SCENARIO_ID.fullmatch(campaign_id):
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
    _safe_child(EVIDENCE_DIR, f"{evidence_id}.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8"
    )
    return evidence_id


def _activate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    record = {
        "scenario_id": scenario["id"],
        "scenario_version": scenario["version"],
        "target": scenario["target"],
        "family": scenario["family"],
        "difficulty": scenario["difficulty"],
        "purple_required": scenario["purple_required"],
        "blind": scenario["blind"],
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    variants = scenario.get("variants", [])
    if scenario.get("blind") and variants:
        variant = secrets.choice(variants)
        nonce = secrets.token_hex(16)
        commitment = hashlib.sha256(
            f"{scenario['id']}:{variant['id']}:{nonce}".encode("utf-8")
        ).hexdigest()
        record.update({
            "variant_id": variant["id"],
            "variant_nonce": nonce,
            "variant_commitment": commitment,
            "variant_count": len(variants),
        })
    _safe_child(STATE_DIR, f"{_declared_id(scenario)}.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8"
    )
    return record


def _clear_scenario_state() -> int:
    removed = 0
    for path in STATE_DIR.glob("*.json"):
        path.unlink()
        removed += 1
    return removed


def _campaign_state_path(campaign: dict[str, Any]) -> Path:
    """Build state paths only from catalog-declared campaign ids, never HTTP path parameters."""
    declared = _validated_name(str(campaign["id"]), SCENARIO_ID)
    return _safe_child(CAMPAIGN_STATE_DIR, f"{declared}.json")


def _snapshot_path(snapshot_id: str) -> Path:
    if not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise HTTPException(status_code=404, detail="snapshot not found")
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        if path.stem == snapshot_id:
            return path
    raise HTTPException(status_code=404, detail="snapshot not found")


app = FastAPI(title="Creation Cyber Range Controller", version="2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": "CYBER_RANGE"}


@app.get("/scenarios")
def list_scenarios() -> dict[str, list[dict[str, Any]]]:
    return {"scenarios": [_public_scenario(item) for item in _load_catalog()]}


@app.get("/campaigns")
def list_campaigns() -> dict[str, list[dict[str, Any]]]:
    return {"campaigns": _load_campaigns()}


@app.get("/state")
def get_range_state() -> dict[str, Any]:
    return {
        "environment": "CYBER_RANGE",
        "scenarios": _state_records(),
        "campaigns": _campaign_records(),
    }


@app.post("/scenarios/{scenario_id}/start")
def start_scenario(scenario_id: str) -> dict[str, Any]:
    return _public_state(_activate_scenario(_scenario(scenario_id)))


@app.post("/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str) -> dict[str, Any]:
    campaign = _campaign(campaign_id)
    path = _campaign_state_path(campaign)
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("status") == "active":
            return current
    _clear_scenario_state()
    first = _activate_scenario(_scenario(campaign["scenario_ids"][0]))
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "campaign_id": campaign_id,
        "campaign_version": campaign["version"],
        "status": "active",
        "current_index": 0,
        "current_scenario_id": first["scenario_id"],
        "completed_scenarios": [],
        "scenario_ids": list(campaign["scenario_ids"]),
        "reset_between_scenarios": campaign["reset_between_scenarios"],
        "blind": campaign["blind"],
        "started_at": now,
        "updated_at": now,
    }
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    _write_audit_record("range_campaign_started", {
        "campaign_id": campaign_id,
        "scenario_id": first["scenario_id"],
        "campaign_version": campaign["version"],
    })
    return record


@app.get("/campaigns/{campaign_id}/state")
def get_campaign_state(campaign_id: str) -> dict[str, Any]:
    campaign = _campaign(campaign_id)
    path = _campaign_state_path(campaign)
    if not path.exists():
        raise HTTPException(status_code=404, detail="campaign has not started")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/campaigns/{campaign_id}/advance")
def advance_campaign(campaign_id: str) -> dict[str, Any]:
    campaign = _campaign(campaign_id)
    path = _campaign_state_path(campaign_id)
    if not path.exists():
        raise HTTPException(status_code=409, detail="campaign has not started")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("status") != "active":
        return record

    current_id = str(record.get("current_scenario_id", ""))
    completed = list(record.get("completed_scenarios", []))
    if current_id and current_id not in completed:
        completed.append(current_id)
    next_index = int(record.get("current_index", 0)) + 1
    if campaign["reset_between_scenarios"]:
        _clear_scenario_state()

    if next_index >= len(campaign["scenario_ids"]):
        record.update({
            "status": "completed",
            "current_index": len(campaign["scenario_ids"]),
            "current_scenario_id": None,
            "completed_scenarios": completed,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        _write_audit_record("range_campaign_completed", {
            "campaign_id": campaign_id,
            "completed_scenarios": completed,
        })
        return record

    next_scenario = _activate_scenario(_scenario(campaign["scenario_ids"][next_index]))
    record.update({
        "current_index": next_index,
        "current_scenario_id": next_scenario["scenario_id"],
        "completed_scenarios": completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    _write_audit_record("range_campaign_advanced", {
        "campaign_id": campaign_id,
        "scenario_id": next_scenario["scenario_id"],
        "completed_scenarios": completed,
    })
    return record


@app.post("/reset")
def reset_range_state() -> dict[str, Any]:
    removed_state = _clear_scenario_state()
    removed_campaigns = 0
    for path in CAMPAIGN_STATE_DIR.glob("*.json"):
        path.unlink()
        removed_campaigns += 1
    return {
        "status": "reset",
        "removed_state_files": removed_state,
        "removed_campaign_state_files": removed_campaigns,
    }


@app.post("/snapshots", status_code=status.HTTP_201_CREATED)
def save_range() -> dict[str, Any]:
    snapshot_id = f"range-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    record = {
        "schema_version": 2,
        "snapshot_id": snapshot_id,
        "environment": "CYBER_RANGE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "state": _state_records(public=False),
        "campaign_state": _campaign_records(),
    }
    destination = _safe_child(SNAPSHOT_DIR, f"{_validated_name(snapshot_id, SNAPSHOT_ID)}.json")
    destination.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    evidence_id = _write_audit_record(
        "range_snapshot_saved",
        {
            "snapshot_id": snapshot_id,
            "state_records": len(record["state"]),
            "campaign_state_records": len(record["campaign_state"]),
        },
    )
    return {
        "snapshot_id": snapshot_id,
        "state_records": len(record["state"]),
        "campaign_state_records": len(record["campaign_state"]),
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
                "campaign_state_records": len(record.get("campaign_state", [])),
            }
        )
    return {"snapshots": snapshots}


@app.post("/snapshots/{snapshot_id}/restore")
def restore_range(snapshot_id: str) -> dict[str, Any]:
    if not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise HTTPException(status_code=404, detail="snapshot not found")
    source = _snapshot_path(snapshot_id)
    try:
        record = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=409, detail="invalid cyber range snapshot") from exc
    if (
        not isinstance(record, dict)
        or record.get("schema_version") not in (1, 2)
        or record.get("environment") != "CYBER_RANGE"
        or record.get("snapshot_id") != snapshot_id
        or not isinstance(record.get("state"), list)
        or (record.get("schema_version") == 2 and not isinstance(record.get("campaign_state"), list))
    ):
        raise HTTPException(status_code=409, detail="invalid cyber range snapshot")

    declared = {item["id"] for item in _load_catalog()}
    prepared: list[tuple[Path, str]] = []
    restored_ids: list[str] = []
    for state_record in record["state"]:
        if not isinstance(state_record, dict):
            raise HTTPException(status_code=409, detail="invalid snapshot state")
        scenario_id = state_record.get("scenario_id")
        if not isinstance(scenario_id, str) or scenario_id not in declared or scenario_id in restored_ids:
            raise HTTPException(status_code=409, detail="invalid snapshot state")
        prepared.append((_safe_child(STATE_DIR, f"{scenario_id}.json"), json.dumps(state_record, sort_keys=True)))
        restored_ids.append(scenario_id)

    declared_campaigns = {item["id"]: item for item in _load_campaigns()}
    campaign_prepared: list[tuple[Path, str]] = []
    restored_campaigns: list[str] = []
    for campaign_record in record.get("campaign_state", []):
        if not isinstance(campaign_record, dict):
            raise HTTPException(status_code=409, detail="invalid campaign snapshot state")
        campaign_id = campaign_record.get("campaign_id")
        campaign = declared_campaigns.get(str(campaign_id))
        scenario_ids = campaign_record.get("scenario_ids")
        if (
            campaign is None
            or campaign_id in restored_campaigns
            or scenario_ids != campaign["scenario_ids"]
            or campaign_record.get("status") not in {"active", "completed"}
        ):
            raise HTTPException(status_code=409, detail="invalid campaign snapshot state")
        campaign_prepared.append((
            _campaign_state_path(campaign),
            json.dumps(campaign_record, sort_keys=True),
        ))
        restored_campaigns.append(str(campaign_id))

    _clear_scenario_state()
    for path in CAMPAIGN_STATE_DIR.glob("*.json"):
        path.unlink()
    for destination, data in prepared:
        destination.write_text(data, encoding="utf-8")
    for destination, data in campaign_prepared:
        destination.write_text(data, encoding="utf-8")

    evidence_id = _write_audit_record(
        "range_snapshot_restored",
        {
            "snapshot_id": snapshot_id,
            "scenario_ids": restored_ids,
            "campaign_ids": restored_campaigns,
        },
    )
    return {
        "snapshot_id": snapshot_id,
        "restored_scenarios": restored_ids,
        "restored_campaigns": restored_campaigns,
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
    destination = _safe_child(EVIDENCE_DIR, f"{evidence_id}.json")
    destination.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return {
        "evidence_id": evidence_id,
        "storage_path": str(destination),
        "scenario_id": request.scenario_id,
    }
