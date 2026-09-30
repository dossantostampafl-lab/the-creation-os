#!/usr/bin/env bash
# Reports how inference is configured, without changing anything.
#
#   sudo ./deploy/oracle/check-inference.sh
#
# It follows the running container rather than this directory: a server can carry more than one
# checkout -- install.sh works where it is, bootstrap-oracle.sh installs into /opt -- and then
# the .env next to you is not the one the API is reading. The key is only ever shown as a
# character count.
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"

# shellcheck source=deploy/oracle/env-file.sh
source "$REPO_DIR/deploy/oracle/env-file.sh"

# The running api container names the directory its Compose project was started from, which is
# the only directory whose .env has any bearing on what the API is doing.
api_container="$(docker ps --filter 'label=com.docker.compose.service=api' --format '{{.ID}}' | head -1)"
if [ -n "$api_container" ]; then
  live_dir="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$api_container" 2>/dev/null)"
else
  live_dir=""
fi

echo "== 0. Which installation is actually running =="
if [ -z "$api_container" ]; then
  echo "   No api container is running anywhere on this machine."
  echo "   Whatever answers on the API port is not a Compose service started from a checkout."
elif [ -z "$live_dir" ]; then
  echo "   An api container is running, but it does not record a project directory."
else
  echo "   The api container was started from: $live_dir"
  if [ "$live_dir" != "$REPO_DIR" ]; then
    echo "   You are in:                        $REPO_DIR"
    echo "   These differ, so THIS directory's .env is not the one the API reads."
    echo "   Set the DEPLOY_REPO_DIR secret to $live_dir so every task acts on the right one."
  fi
fi

env_dir="${live_dir:-$REPO_DIR}"
echo
echo "== 1. What .env holds (in $env_dir) =="
if [ ! -f "$env_dir/.env" ]; then
  echo "   There is no .env there."
else
  (
    cd "$env_dir"
    printf '   LLM_PROVIDER=%s\n' "$(env_get LLM_PROVIDER)"
    printf '   LLM_FALLBACK_PROVIDERS=%s\n' "$(env_get LLM_FALLBACK_PROVIDERS)"
    printf '   FREELLMAPI_MODEL=%s\n' "$(env_get FREELLMAPI_MODEL)"
    printf '   FREELLMAPI_BASE_URL=%s\n' "$(env_get FREELLMAPI_BASE_URL)"
    freellm_key="$(env_get FREELLMAPI_API_KEY)"
    printf '   FREELLMAPI_API_KEY: %s\n' "$([ -n "$freellm_key" ] && echo "set, ${#freellm_key} characters" || echo "EMPTY (allowed)")"
    printf '   ANTHROPIC_MODEL=%s\n' "$(env_get ANTHROPIC_MODEL)"
    workspace="$(env_get ANTHROPIC_WORKSPACE_ID)"
    printf '   ANTHROPIC_WORKSPACE_ID=%s\n' "${workspace:-<empty, which is the usual case>}"
    key="$(env_get ANTHROPIC_API_KEY)"
    printf '   ANTHROPIC_API_KEY: %s\n' "$([ -n "$key" ] && echo "set, ${#key} characters" || echo "EMPTY")"
  )
fi

echo
echo "== 2. What the running container received =="
if [ -z "$api_container" ]; then
  echo "   No api container to ask."
else
  docker exec -i "$api_container" sh -c \
    'printf "   LLM_PROVIDER=%s\n   LLM_FALLBACK_PROVIDERS=%s\n   FREELLMAPI_MODEL=%s\n   FREELLMAPI_BASE_URL=%s\n   FREELLMAPI_API_KEY: %s characters\n   ANTHROPIC_MODEL=%s\n   ANTHROPIC_API_KEY: %s characters\n" \
      "$LLM_PROVIDER" "$LLM_FALLBACK_PROVIDERS" "$FREELLMAPI_MODEL" "$FREELLMAPI_BASE_URL" "${#FREELLMAPI_API_KEY}" \
      "$ANTHROPIC_MODEL" "${#ANTHROPIC_API_KEY}"' \
    || echo "   Could not read the container's environment."
fi

echo
echo "== 3. What the API reports =="
port="$(cd "$env_dir" 2>/dev/null && env_get CREATION_API_PORT)"
base="http://127.0.0.1:${port:-8000}"
username="$(cd "$env_dir" 2>/dev/null && env_get CREATOR_BOOTSTRAP_USERNAME)"
password="$(cd "$env_dir" 2>/dev/null && env_get CREATOR_BOOTSTRAP_PASSWORD)"
login_body="$(python3 -c 'import json, sys; print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))' \
  "$username" "$password")"
token="$(
  curl -fsS -X POST "$base/api/v1/auth/login" -H 'Content-Type: application/json' -d "$login_body" 2>/dev/null \
    | python3 -c 'import json, sys
try:
    print(json.load(sys.stdin).get("access_token", ""))
except Exception:
    print("")' || true
)"
unset login_body password

if [ -z "$token" ]; then
  echo "   Could not log in with the credentials in $env_dir/.env."
  echo "   The Creator's password in the database is not the one that .env holds."
  echo "   rotate-creator-password gives the Creator the password .env holds, after a restart."
else
  curl -fsS -H "Authorization: Bearer $token" "$base/api/v1/system/inference" 2>/dev/null \
    | python3 -c 'import json, sys
snapshot = json.load(sys.stdin)
print("   configured:", snapshot.get("configured"))
print("   provider:  ", snapshot.get("configured_provider"))
for entry in snapshot.get("providers", []):
    print("   -", entry.get("provider"), "available:", entry.get("available"), entry.get("detail") or "")' \
    || echo "   Could not read the status."
fi

# A provider that loads but answers "unavailable" says only that something upstream refused.
# The provider's own words are what identify it, so ask it directly, from inside the container
# that holds the credential. The reply carries no secret.
echo
echo "== 4. What Anthropic itself says =="
if [ -z "$api_container" ]; then
  echo "   No api container to ask from."
else
  docker exec -i "$api_container" python -c '
import json
import os

import httpx

key = os.getenv("ANTHROPIC_API_KEY", "")
model = os.getenv("ANTHROPIC_MODEL", "")
if not key:
    raise SystemExit("   The container has no ANTHROPIC_API_KEY.")
if not model:
    raise SystemExit("   The container has no ANTHROPIC_MODEL.")

headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
if workspace:
    headers["anthropic-workspace-id"] = workspace

base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
print(f"   Asking {base}/models/{model}")
try:
    response = httpx.get(f"{base}/models/{model}", headers=headers, timeout=20)
except Exception as exc:  # the network itself, not the API
    raise SystemExit(f"   The request never arrived: {type(exc).__name__}: {exc}")

print(f"   HTTP {response.status_code}")
try:
    body = response.json()
except ValueError:
    print("   " + response.text[:300])
else:
    # An error body names the cause; a success body names the model. Neither carries the key.
    print("   " + json.dumps(body)[:400])
' || echo "   Could not run the probe inside the container."
fi


# FreeLLMAPI can be installed and healthy even while another provider is primary. Probe it
# independently so the report answers both questions: provider order and gateway availability.
echo
echo "== 5. What FreeLLMAPI itself says =="
if [ -z "$api_container" ]; then
  echo "   No api container to ask from."
else
  docker exec -i "$api_container" python -c '
import json
import os

import httpx

base = os.getenv("FREELLMAPI_BASE_URL", "").strip() or "http://host.docker.internal:3001/v1"
key = os.getenv("FREELLMAPI_API_KEY", "").strip()
headers = {"Authorization": f"Bearer {key}"} if key else {}
print(f"   Asking {base.rstrip('/')}/models")
try:
    response = httpx.get(f"{base.rstrip('/')}/models", headers=headers, timeout=20)
except Exception as exc:
    raise SystemExit(f"   The request never arrived: {type(exc).__name__}: {exc}")

print(f"   HTTP {response.status_code}")
try:
    body = response.json()
except ValueError:
    print("   " + response.text[:300])
else:
    print("   " + json.dumps(body)[:400])
' || echo "   Could not run the FreeLLMAPI probe inside the container."
fi
