#!/usr/bin/env bash
# Exercises the running application the way a Creator does, and says what worked.
#
#   sudo ./deploy/oracle/smoke-test.sh          # read-only checks
#   sudo ./deploy/oracle/smoke-test.sh --deus   # also checks three DEUS conversation turns
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

# Prove the actual local speech models can synthesize Portuguese, transcribe it
# back through Vosk and recognize the "Deus" wake word before calling the UI ready.
if docker exec "$container" python -c "from app.config import settings; raise SystemExit(0 if settings.deus_voice_session_enabled else 1)" >/dev/null 2>&1; then
  echo "== Local wake-word speech self-test =="
  docker exec "$container" python -m app.voice_session.verify_local
fi

frontend_source_sha="$(cd frontend && { find src public -type f -print; printf '%s\n' package.json package-lock.json vite.config.ts nginx.conf; } | sort | xargs sha256sum | sha256sum | awk '{print $1}')"

docker exec -i -e TCO_WITH_DEUS="$with_deus" "$container" python - "$frontend_source_sha" <<'PY'
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
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


def deus_probe_matches(answer: str, expected: tuple[str, ...] | str | None) -> bool:
    normalized = unicodedata.normalize("NFKD", answer.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = " ".join(re.sub(r"[^\w\s]", " ", normalized).split())
    if not normalized:
        return False
    if isinstance(expected, tuple):
        words = normalized.split()
        return all(any(word.startswith(stem) for word in words) for stem in expected)
    if isinstance(expected, str):
        return normalized == expected
    return True


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

    expected_frontend_source = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    frontend_source = client.get(f"{FRONTEND}/frontend-source.sha256")
    deployed_frontend_source = frontend_source.text.strip() if frontend_source.status_code == 200 else ""
    report(
        "frontend bundle matches deployed source",
        bool(expected_frontend_source)
        and frontend_source.status_code == 200
        and deployed_frontend_source == expected_frontend_source,
        deployed_frontend_source[:16] if deployed_frontend_source else f"HTTP {frontend_source.status_code}",
    )

    print()
    print("== Reading the system ==")
    # Each of these backs a section of the interface; a failure here is a blank panel there.
    for name, path in [
        ("universes", "/universes"),
        ("agents", "/agents"),
        ("training dashboard", "/cyber-range/training"),
        ("build downloads catalog", "/builds"),
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

    builds = client.get("/builds")
    if builds.status_code == 200 and builds.json().get("status") == "available":
        for artifact in builds.json().get("files", []):
            download = client.get(f"/builds/{artifact['id']}/download")
            valid = (download.status_code == 200
                     and len(download.content) == artifact["size_bytes"]
                     and hashlib.sha256(download.content).hexdigest() == artifact["sha256"])
            report(f"authenticated download {artifact['id']}", valid, f"HTTP {download.status_code}")
    elif builds.status_code == 200:
        print("   INFO  Android artifacts have not been published yet; no download was certified.")

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
    configured_provider = str(snapshot.get("configured_provider") or "").lower()
    available = any(p.get("available") for p in snapshot.get("providers", []))
    chatgpt_credentials = os.getenv(
        "CHATGPT_CREDENTIALS_FILE",
        "/var/lib/creation/chatgpt/credentials.json",
    )
    chatgpt_preauth = (
        configured_provider == "chatgpt"
        and not os.path.isfile(chatgpt_credentials)
    )
    report("inference configured", configured, configured_provider)
    # Before the one-time browser OAuth, an explicitly selected ChatGPT provider is expected
    # to be unavailable. Treat that state as deployment-ready, not as a broken provider.
    if chatgpt_preauth:
        report("ChatGPT OAuth pending", True, "deployment is ready for authentication")
    else:
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
    diagnostics_enabled = os.getenv("DEUS_DIAGNOSTICS_ENABLED", "").lower() == "true"
    training_enabled = os.getenv("STF_AUTO_TRAINING_ENABLED", "").lower() == "true"
    if diagnostics_enabled or training_enabled:
        async def check_connected_runtime():
            from datetime import datetime, timedelta, timezone
            from sqlalchemy import func, select
            from app.db.session import AsyncSessionLocal
            from app.diagnostics.heartbeat import ServiceHeartbeat
            from app.models.entities import Agent
            from app.models.security_task_force import StfRun
            from app.security_task_force.training import TRAINING_AGENT_SPECS, training_run_filter

            expected = set()
            if diagnostics_enabled:
                expected.update({"task-worker", "knowledge-worker", "diagnostics-worker"})
                if os.getenv("DEUS_AUTONOMY_DISCOVERY_ENABLED", "").lower() == "true":
                    expected.add("discovery-worker")
                if os.getenv("DEUS_AUTONOMY_COMPETITION_ENABLED", "").lower() == "true":
                    expected.add("opportunity-worker")
            if training_enabled:
                expected.add("stf-training-worker")

            async with AsyncSessionLocal() as session:
                services = set(await session.scalars(select(ServiceHeartbeat.service).where(
                    ServiceHeartbeat.valid_until > datetime.now(timezone.utc))))
                missing = sorted(expected - services)
                training_agents = training_runs = None
                stalled_training = 0
                if training_enabled:
                    codes = [item.code for item in TRAINING_AGENT_SPECS]
                    training_agents = int(await session.scalar(
                        select(func.count()).select_from(Agent).where(
                            Agent.code.in_(codes)
                        )
                    ) or 0)
                    training_runs = int(await session.scalar(
                        select(func.count()).select_from(StfRun).where(
                            training_run_filter()
                        )
                    ) or 0)
                    stalled_training = int(await session.scalar(
                        select(func.count()).select_from(StfRun).where(
                            training_run_filter(),
                            StfRun.state == 'QUEUED',
                            StfRun.created_at < datetime.now(timezone.utc) - timedelta(minutes=5),
                        )
                    ) or 0)
            return missing, training_agents, training_runs, stalled_training

        try:
            missing, training_agents, training_runs, stalled_training = asyncio.run(check_connected_runtime())
            report("connected worker heartbeats", not missing,
                   "fresh" if not missing else "missing: " + ", ".join(missing))
            if training_enabled:
                report("10 STF Cyber Range training agents registered",
                       training_agents == 10, str(training_agents))
                report("automatic STF training registered",
                       bool(training_runs and training_runs > 0), f"{training_runs or 0} run(s)")
                report("training queue advances within five minutes", stalled_training == 0,
                       f"{stalled_training} stalled queued run(s)")
                async def check_temporal():
                    from datetime import timedelta
                    from temporalio.client import Client
                    from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
                    temporal = await Client.connect('stf-temporal:7233')
                    await temporal.workflow_service.describe_namespace(
                        DescribeNamespaceRequest(namespace=temporal.namespace),
                        timeout=timedelta(seconds=5),
                    )
                try:
                    asyncio.run(asyncio.wait_for(check_temporal(), timeout=10))
                    report("Temporal accepts private workflow clients", True)
                except Exception as exc:
                    report("Temporal accepts private workflow clients", False, type(exc).__name__)
        except Exception as exc:
            report("connected runtime database checks", False, type(exc).__name__)

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

    if os.getenv("TCO_WITH_DEUS") == "true" and chatgpt_preauth:
        print()
        print("== Talking to DEUS ==")
        print("   INFO  skipped until the one-time Sign in with ChatGPT OAuth is imported.")
    elif os.getenv("TCO_WITH_DEUS") == "true":
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
            probes = [
                ("Deus, prefiro sua voz masculina, grave e serena. Confirme minha preferência em uma frase.",
                 None, "preference acknowledgement"),
                ("Qual estilo de voz eu acabei de preferir? Responda em uma frase.",
                 ("masculin", "grav", "seren"), "contextual voice preference recall"),
                ("Responda apenas: voz local ativa", "voz local ativa", "exact instruction adherence"),
            ]
            for turn_index, (prompt, expected, check_name) in enumerate(probes, start=1):
                started = time.monotonic()
                reply = client.post(
                    f"/conversations/{conversation_id}/deus",
                    json={
                        "content": prompt,
                        "request_id": str(uuid.uuid4()),
                    },
                )
                elapsed = time.monotonic() - started
                if reply.status_code in (200, 201):
                    body = reply.json()
                    answer = (body.get("response") or "").strip()
                    ok = deus_probe_matches(answer, expected)
                    successful_turns += int(ok)
                    # Which provider answered, and why the first choice did not, if it did not.
                    via = body.get("provider") or "?"
                    if body.get("fallback_from"):
                        via += f" after {body['fallback_from']} failed ({body.get('fallback_reason')})"
                    report(f"DEUS turn {turn_index}: {check_name}", ok, f"{elapsed:.2f}s / {via} / {answer[:160]!r}")
                else:
                    try:
                        failure = reply.json().get("detail") or {}
                    except ValueError:
                        failure = {}
                    if isinstance(failure, dict) and failure.get("code"):
                        # Codes and statuses only: this output lands in a public Actions log.
                        summary = f"{failure.get('provider')}: {failure.get('code')} (upstream {failure.get('upstream_status')})"
                        if failure.get("fallback_from"):
                            summary += (f"; first {failure['fallback_from']}: {failure.get('fallback_reason')}"
                                        f" (upstream {failure.get('fallback_upstream_status')})")
                    else:
                        summary = reply.text[:160]
                    report(f"DEUS turn {turn_index}: {check_name}", False,
                           f"{elapsed:.2f}s / HTTP {reply.status_code}: {summary}")
            report("DEUS sustained 3 consecutive turns", successful_turns == 3, f"{successful_turns}/3")
            messages = client.get(f"/conversations/{conversation_id}/messages")
            report("all DEUS turns are stored", messages.status_code == 200 and len(messages.json()) >= 6,
                   f"{len(messages.json())} message(s)" if messages.status_code == 200 else "")

print()
print(f"== {passed} passed, {failed} failed ==")
sys.exit(1 if failed else 0)
PY
