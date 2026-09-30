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
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import connect as websocket_connect

BASE = "http://127.0.0.1:8000/api/v1"
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

    print()
    print("== Voice ==")
    voice = client.post("/voice/synthesize", json={"text": "Teste."})
    if voice.status_code == 200:
        report("ElevenLabs synthesis", True, f"{len(voice.content)} bytes of audio")
    elif voice.status_code == 501:
        report("ElevenLabs synthesis", False, "501: realtime ElevenLabs voice is disabled or has no key")
    else:
        report("ElevenLabs synthesis", False, f"HTTP {voice.status_code}")

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
                            f"ws://127.0.0.1:8000/api/v1/voice/session?{query}",
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

            reply = client.post(
                f"/conversations/{conversation_id}/deus",
                json={"content": "Responda apenas: estou aqui."},
            )
            # The endpoint answers 201: it created a message. Accepting only 200 reported a
            # working DEUS as broken, which is the one wrong answer a health check must not give.
            if reply.status_code in (200, 201):
                text = (reply.json().get("response") or "").strip()
                report("DEUS replies", bool(text), f"{text[:80]!r}")
            else:
                report("DEUS replies", False, f"HTTP {reply.status_code}: {reply.text[:160]}")
            messages = client.get(f"/conversations/{conversation_id}/messages")
            report("the reply is stored", messages.status_code == 200 and len(messages.json()) >= 2,
                   f"{len(messages.json())} message(s)" if messages.status_code == 200 else "")

print()
print(f"== {passed} passed, {failed} failed ==")
sys.exit(1 if failed else 0)
PY
