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
import os
import sys

import httpx

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
        report("ElevenLabs synthesis", False, "501: disabled or no key -- the browser voice is used")
    else:
        report("ElevenLabs synthesis", False, f"HTTP {voice.status_code}")

    if os.getenv("TCO_WITH_DEUS") == "true":
        print()
        print("== Talking to DEUS ==")
        conversation = client.post("/conversations", json={"title": "Smoke test"})
        if conversation.status_code not in (200, 201):
            report("create conversation", False, f"HTTP {conversation.status_code}")
        else:
            conversation_id = conversation.json()["id"]
            report("create conversation", True)
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
