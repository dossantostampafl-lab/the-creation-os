#!/usr/bin/env bash
# Exercises the running application the way a Creator does, and says what worked.
#
#   sudo ./deploy/oracle/smoke-test.sh          # read-only checks
#   sudo ./deploy/oracle/smoke-test.sh --deus   # also sends one message to DEUS (costs a call)
#
# It runs inside the api container, so the credentials it logs in with are the ones already in
# that process's environment: nothing is passed on a command line, where the server's process
# list would show it.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

with_deus=false
[ "${1:-}" = "--deus" ] && with_deus=true

container="$(docker ps --filter 'label=com.docker.compose.service=api' --format '{{.ID}}' | head -1)"
if [ -z "$container" ]; then
  echo "No api container is running." >&2
  exit 1
fi

docker exec -i -e TCO_WITH_DEUS="$with_deus" "$container" python - <<'PY'
import asyncio
import json
import os
import sys
import uuid
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import connect as websocket_connect

# Use the dashboard proxy, not API loopback: voice must work through nginx too.
FRONTEND = "http://frontend:8080"
BASE = f"{FRONTEND}/api/v1"
passed = failed = 0


def report(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"   PASS  {name}{'  ' + detail if detail else ''}")
    else:
        failed += 1
        print(f"   FAIL  {name}  {detail}")


with httpx.Client(base_url=BASE, timeout=45) as client:
    print("== Signing in ==")
    credentials = {
        "username": os.getenv("CREATOR_BOOTSTRAP_USERNAME", ""),
        "password": os.getenv("CREATOR_BOOTSTRAP_PASSWORD", ""),
    }
    login = client.post("/auth/login", json=credentials)
    if login.status_code != 200:
        print(f"   FAIL  login  HTTP {login.status_code}")
        print("   The password in .env is not the Creator's. Run set-creator-password.")
        raise SystemExit(1)
    token = login.json().get("access_token", "")
    report("login", bool(token))
    client.headers["Authorization"] = f"Bearer {token}"

    print()
    print("== Reading the system ==")
    # Each of these backs a section of the interface; a failure here is a blank panel there.
    for name, path in [
        ("universes", "/universes"),
        ("agents", "/agents"),
        ("missions", "/missions"),
        ("inceptions", "/inceptions"),
        ("conversations", "/conversations"),
        ("chronicles", "/chronicles?limit=5&offset=0"),
        ("chronicle integrity", "/chronicles/verify"),
        ("pulse", "/pulse"),
        ("system state", "/system/state?page=1&page_size=5"),
        ("projections", "/system/projections"),
        ("cache", "/system/cache"),
        ("opportunity projection", "/opportunities/projection"),
    ]:
        try:
            response = client.get(path)
        except Exception as exc:
            report(name, False, f"{type(exc).__name__}: {exc}")
            continue
        ok = response.status_code == 200
        detail = f"HTTP {response.status_code}"
        if ok:
            body = response.json()
            if isinstance(body, list):
                detail = f"{len(body)} item(s)"
            elif isinstance(body, dict) and "items" in body:
                detail = f"{len(body['items'])} item(s) of {body.get('total', '?')}"
            else:
                detail = ""
        report(name, ok, detail)

    # The count alone hid three legacy rows that the canonical seeder cannot match, because it
    # reconciles by code and theirs are not canonical codes. Naming them makes that visible.
    print()
    print("== Universes ==")
    catalog = client.get("/universes")
    if catalog.status_code == 200:
        CANONICAL = {
            "knowledge", "engineering", "security", "vision", "design", "business",
            "marketing", "legal", "finance", "automation", "communication", "evolution",
        }
        rows = catalog.json()
        seen = {str(row.get("code")) for row in rows}
        active_seen = {str(row.get("code")) for row in rows if row.get("active")}
        for row in sorted(rows, key=lambda r: str(r.get("code"))):
            code = str(row.get("code"))
            mark = "canonical" if code in CANONICAL else "NOT CANONICAL"
            state = "active" if row.get("active") else "inactive"
            print(f"   {code:16} {state:9} {mark}   {row.get('name', '')}")
        missing_active = sorted(CANONICAL - active_seen)
        report("the 12 canonical Universes are active", not missing_active,
               f"missing or inactive: {missing_active}" if missing_active else "")
        extra_active = sorted(active_seen - CANONICAL)
        report("no active Universe outside the canon", not extra_active,
               f"active extra: {extra_active}" if extra_active else "")
    else:
        report("universe catalog", False, f"HTTP {catalog.status_code}")

    print()
    print("== Inference ==")
    inference = client.get("/system/inference")
    snapshot = inference.json() if inference.status_code == 200 else {}
    configured = bool(snapshot.get("configured"))
    available = any(p.get("available") for p in snapshot.get("providers", []))
    report("inference configured", configured, snapshot.get("configured_provider", ""))
    # This is the exact expression the interface uses to enable the DEUS console.
    report("a provider is available", available,
           "" if available else "the console stays disabled while this is false")

    if os.getenv("LLM_PROVIDER", "").lower() == "freellmapi" and os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL"):
        reserve = [item.strip().lower() for item in os.getenv("LLM_FALLBACK_PROVIDERS", "").split(",") if item.strip()]
        report("Anthropic inference reserve configured", "anthropic" in reserve,
               ",".join(reserve) if reserve else "reserve chain is empty")

    if os.getenv("DEUS_CONTEXT_RETRIEVAL_ENABLED", "").lower() == "true":
        print("== Connected DEUS ==")
        for name, path in [("knowledge projects", "/knowledge/projects"),
                           ("current diagnostics", "/knowledge/diagnostics/current"),
                           ("Cyber Range configuration", "/cyber-range/status")]:
            response = client.get(path)
            detail = f"HTTP {response.status_code}"
            if name == "Cyber Range configuration" and response.status_code == 200:
                detail = response.json().get("status", "unknown")
            report(name, response.status_code == 200, detail)
            if name == "current diagnostics" and response.status_code == 200 and os.getenv("DEUS_DIAGNOSTICS_ENABLED", "").lower() == "true":
                diagnostic_snapshot = response.json()
                observations = diagnostic_snapshot.get("observations", [])
                report("diagnostic observations available", bool(observations), f"{len(observations)} observation(s)")
                report("diagnostic observer heartbeat", diagnostic_snapshot.get("observer_status") == "healthy",
                       str(diagnostic_snapshot.get("observer_status", "unknown")))
            if name == "Cyber Range configuration" and response.status_code == 200 and os.getenv("STF_AUTO_TRAINING_ENABLED", "").lower() == "true":
                report("Cyber Range available for automatic training", response.json().get("status") == "available",
                       str(response.json().get("status", "unknown")))
        if os.getenv("DEUS_DIAGNOSTICS_ENABLED", "").lower() == "true":
            async def check_connected_runtime():
                from datetime import datetime, timezone
                from sqlalchemy import func, select
                from app.db.session import AsyncSessionLocal
                from app.diagnostics.heartbeat import ServiceHeartbeat
                expected = {"task-worker", "knowledge-worker", "diagnostics-worker"}
                training_enabled = os.getenv("STF_AUTO_TRAINING_ENABLED", "").lower() == "true"
                if os.getenv("DEUS_AUTONOMY_DISCOVERY_ENABLED", "").lower() == "true":
                    expected.add("discovery-worker")
                # Production competition is only healthy when its supervised worker
                # is emitting a fresh heartbeat; code deployment alone is not enough.
                if os.getenv("DEUS_AUTONOMY_COMPETITION_ENABLED", "").lower() == "true":
                    expected.add("opportunity-worker")
                if training_enabled:
                    expected.add("stf-training-worker")
                async with AsyncSessionLocal() as session:
                    services = set(await session.scalars(select(ServiceHeartbeat.service).where(
                        ServiceHeartbeat.valid_until > datetime.now(timezone.utc))))
                    missing = sorted(expected - services)
                    training_agents = training_runs = None
                    if training_enabled:
                        from app.models.entities import Agent
                        from app.models.security_task_force import StfRun
                        from app.security_task_force.training import TRAINING_AGENT_SPECS, training_mission_id
                        codes = [item.code for item in TRAINING_AGENT_SPECS]
                        missions = [training_mission_id(item.code) for item in TRAINING_AGENT_SPECS]
                        training_agents = int(await session.scalar(
                            select(func.count()).select_from(Agent).where(
                                Agent.code.in_(codes), Agent.active.is_(True)
                            )
                        ) or 0)
                        training_runs = int(await session.scalar(
                            select(func.count()).select_from(StfRun).where(
                                StfRun.mission_id.in_(missions)
                            )
                        ) or 0)
                return (
                    not missing,
                    "fresh" if not missing else "missing: " + ", ".join(missing),
                    training_agents,
                    training_runs,
                )
            try:
                heartbeat_ok, heartbeat_detail, training_agents, training_runs = asyncio.run(check_connected_runtime())
                report("connected worker heartbeats", heartbeat_ok, heartbeat_detail)
                if os.getenv("STF_AUTO_TRAINING_ENABLED", "").lower() == "true":
                    report("10 STF Cyber Range training agents active", training_agents == 10, str(training_agents))
                    report("automatic STF training has started", bool(training_runs and training_runs > 0),
                           f"{training_runs or 0} run(s)")
            except Exception as exc:
                report("connected runtime state", False, type(exc).__name__)

    print()
    print("== Voice ==")
    worklet = client.get(f"{FRONTEND}/voice/pcm-capture.worklet.js")
    report(
        "microphone worklet served by dashboard",
        worklet.status_code == 200
        and "javascript" in worklet.headers.get("content-type", "")
        and "registerProcessor" in worklet.text,
        f"HTTP {worklet.status_code}",
    )
    acknowledgement = client.get("/voice/session/acknowledgement")
    report(
        "DEUS wake acknowledgement",
        acknowledgement.status_code == 200 and len(acknowledgement.content) > 0
        and acknowledgement.headers.get("X-DEUS-Audio-Format") == "pcm_s16le",
        f"HTTP {acknowledgement.status_code}",
    )
    ticket_probe = client.post("/voice/session/ticket")
    report(
        "realtime voice ticket",
        ticket_probe.status_code == 201 and bool(ticket_probe.json().get("ticket")),
        f"HTTP {ticket_probe.status_code}",
    )

    if os.getenv("TCO_WITH_DEUS") == "true":
        print()
        print("== Talking to DEUS ==")
        conversation = client.post("/conversations", json={"title": "Smoke test"})
        if conversation.status_code not in (200, 201):
            report("create conversation", False, f"HTTP {conversation.status_code}")
        else:
            conversation_id = conversation.json()["id"]
            report("create conversation", True)

            realtime_ticket = client.post("/voice/session/ticket")
            if realtime_ticket.status_code == 201:
                async def verify_realtime_session() -> tuple[bool, str]:
                    query = urlencode({
                        "ticket": realtime_ticket.json()["ticket"],
                        "conversation_id": conversation_id,
                    })
                    try:
                        async with websocket_connect(
                            f"ws://frontend:8080/api/v1/voice/session?{query}",
                            open_timeout=20,
                        ) as websocket:
                            raw = await asyncio.wait_for(websocket.recv(), timeout=20)
                            event = json.loads(raw)
                            ok = (
                                event.get("type") == "session_ready"
                                and event.get("state") == "ARMED"
                                and bool(event.get("session_id"))
                            )
                            if ok:
                                await websocket.send(json.dumps({
                                    "type": "stop",
                                    "session_id": event["session_id"],
                                    "turn_id": event.get("turn_id", 0),
                                }))
                            return ok, f"{event.get('type')} / {event.get('state')}"
                    except Exception as exc:
                        return False, f"{type(exc).__name__}: {exc}"

                voice_ok, voice_detail = asyncio.run(verify_realtime_session())
                report("realtime DEUS voice session", voice_ok, voice_detail)
            else:
                report("realtime DEUS voice session", False, f"ticket HTTP {realtime_ticket.status_code}")

            successful_turns = 0
            for turn_index in range(1, 4):
                reply = client.post(
                    f"/conversations/{conversation_id}/deus",
                    json={
                        "content": f"Responda brevemente em português ao turno {turn_index}.",
                        "request_id": str(uuid.uuid4()),
                    },
                )
                if reply.status_code in (200, 201):
                    answer = (reply.json().get("response") or "").strip()
                    ok = bool(answer)
                    successful_turns += int(ok)
                    report(f"DEUS turn {turn_index}", ok, f"{answer[:80]!r}")
                else:
                    report(f"DEUS turn {turn_index}", False, f"HTTP {reply.status_code}: {reply.text[:160]}")
            report("DEUS sustained 3 consecutive turns", successful_turns == 3, f"{successful_turns}/3")
            messages = client.get(f"/conversations/{conversation_id}/messages")
            report("all DEUS turns are stored", messages.status_code == 200 and len(messages.json()) >= 6,
                   f"{len(messages.json())} message(s)" if messages.status_code == 200 else "")

print()
print(f"== {passed} passed, {failed} failed ==")
sys.exit(1 if failed else 0)
PY
