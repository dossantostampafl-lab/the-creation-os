#!/usr/bin/env bash
# Reports how inference is configured, without changing anything.
#
#   sudo ./deploy/oracle/check-inference.sh
#
# It answers the three questions in order, because a wrong answer at one step explains the
# next: what .env holds, what the running container received from it, and what the API itself
# reports. The key is only ever shown as a character count.
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

# shellcheck source=deploy/oracle/env-file.sh
source "$REPO_DIR/deploy/oracle/env-file.sh"

if [ ! -f .env ]; then
  echo "There is no .env in $REPO_DIR. Run deploy/oracle/install.sh first." >&2
  exit 1
fi

echo "== 1. What .env holds =="
printf '   LLM_PROVIDER=%s\n' "$(env_get LLM_PROVIDER)"
printf '   ANTHROPIC_MODEL=%s\n' "$(env_get ANTHROPIC_MODEL)"
workspace="$(env_get ANTHROPIC_WORKSPACE_ID)"
printf '   ANTHROPIC_WORKSPACE_ID=%s\n' "${workspace:-<empty, which is the usual case>}"
key="$(env_get ANTHROPIC_API_KEY)"
printf '   ANTHROPIC_API_KEY: %s\n' "$([ -n "$key" ] && echo "set, ${#key} characters" || echo "EMPTY")"
unset key

echo
echo "== 2. What the running container received =="
if ! "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx api; then
  echo "   The api container is not running. Start it with:"
  echo "   sudo docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d"
else
  "${COMPOSE[@]}" exec -T api sh -c \
    'printf "   LLM_PROVIDER=%s\n   ANTHROPIC_MODEL=%s\n   ANTHROPIC_API_KEY: %s characters\n" \
      "$LLM_PROVIDER" "$ANTHROPIC_MODEL" "${#ANTHROPIC_API_KEY}"' \
    || echo "   Could not read the container's environment."
fi

echo
echo "== 3. What the API reports =="
port="$(env_get CREATION_API_PORT)"
base="http://127.0.0.1:${port:-8000}"
login_body="$(python3 -c 'import json, sys; print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))' \
  "$(env_get CREATOR_BOOTSTRAP_USERNAME)" "$(env_get CREATOR_BOOTSTRAP_PASSWORD)")"
token="$(
  curl -fsS -X POST "$base/api/v1/auth/login" -H 'Content-Type: application/json' -d "$login_body" 2>/dev/null \
    | python3 -c 'import json, sys
try:
    print(json.load(sys.stdin).get("access_token", ""))
except Exception:
    print("")' || true
)"
unset login_body

if [ -z "$token" ]; then
  echo "   Could not log in with the credentials in .env."
  echo "   The Creator's password in the database is not the one .env holds."
  echo "   sudo docker compose -f docker-compose.yml -f docker-compose.cloud.yml exec api rotate-creator-password"
  echo "   gives the Creator the password .env holds, after a restart so the API reads it."
  exit 0
fi

curl -fsS -H "Authorization: Bearer $token" "$base/api/v1/system/inference" 2>/dev/null \
  | python3 -c 'import json, sys
snapshot = json.load(sys.stdin)
print("   configured:", snapshot.get("configured"))
print("   provider:  ", snapshot.get("configured_provider"))
for entry in snapshot.get("providers", []):
    print("   -", entry.get("provider"), "available:", entry.get("available"), entry.get("detail") or "")' \
  || echo "   Could not read the status."
