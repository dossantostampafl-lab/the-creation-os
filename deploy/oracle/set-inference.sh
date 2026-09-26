#!/usr/bin/env bash
# Points a running installation at a real inference provider, then restarts what reads the
# configuration and reports what the API itself now says.
#
#   sudo ./deploy/oracle/set-inference.sh              # anthropic, asks for the key
#   sudo ./deploy/oracle/set-inference.sh anthropic claude-sonnet-5
#
# The key is read with the terminal echo off, so it is never shown and never reaches the shell
# history. It is written to .env as literal text: a key containing a shell or regex metacharacter
# (a '|', an '&', a backslash) is written exactly as pasted.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

# shellcheck source=deploy/oracle/env-file.sh
source "$REPO_DIR/deploy/oracle/env-file.sh"

if [ ! -f .env ]; then
  echo "There is no .env here. Run deploy/oracle/install.sh first." >&2
  exit 1
fi

provider="${1:-anthropic}"
case "$provider" in
  anthropic) key_var=ANTHROPIC_API_KEY; model_var=ANTHROPIC_MODEL; default_model=claude-sonnet-5 ;;
  openai) key_var=LLM_API_KEY; model_var=LLM_MODEL; default_model=gpt-4o-mini ;;
  freellmapi) key_var=FREELLMAPI_API_KEY; model_var=FREELLMAPI_MODEL; default_model="" ;;
  openai_compatible) key_var=OPENAI_COMPATIBLE_API_KEY; model_var=OPENAI_COMPATIBLE_MODEL; default_model="" ;;
  *)
    echo "Unknown provider: $provider" >&2
    echo "Use one of: anthropic, openai, freellmapi, openai_compatible" >&2
    exit 1
    ;;
esac

model="${2:-$default_model}"
if [ -z "$model" ]; then
  read -rp "Model for $provider: " model
fi
if [ -z "$model" ]; then
  echo "A model is required." >&2
  exit 1
fi

# -s keeps the key off the screen; -r stops a backslash in it from being eaten.
read -rsp "Paste the $provider API key and press Enter: " api_key
echo
if [ -z "$api_key" ]; then
  echo "No key was pasted; nothing changed." >&2
  exit 1
fi
# The length is the one safe thing to show: it catches a paste that arrived truncated.
printf 'Key received: %s characters.\n' "${#api_key}"

cp .env .env.bak
chmod 600 .env.bak
env_set LLM_PROVIDER "$provider"
env_set "$model_var" "$model"
env_set "$key_var" "$api_key"
unset api_key
chmod 600 .env

echo "Written to .env (the previous file is kept as .env.bak):"
printf '  LLM_PROVIDER=%s\n' "$(env_get LLM_PROVIDER)"
printf '  %s=%s\n' "$model_var" "$(env_get "$model_var")"
if [ -n "$(env_get "$key_var")" ]; then
  printf '  %s=<set>\n' "$key_var"
else
  echo "The key was not written. .env.bak still holds the previous file." >&2
  exit 1
fi

# The containers read .env only when they are created, so recreating them is part of the change.
echo
echo "Restarting api and worker..."
"${COMPOSE[@]}" up -d --force-recreate api worker

port="$(env_get CREATION_API_PORT)"
base="http://127.0.0.1:${port:-8000}"
printf '\nWaiting for the API'
for _ in $(seq 1 60); do
  if curl -fsS "$base/api/v1/health/ready" >/dev/null 2>&1; then
    break
  fi
  printf '.'
  sleep 2
done
echo

# The API reports the provider it actually loaded, which is the only answer that counts.
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
  echo "Could not log in to read the status. Check it in the interface, under System."
  exit 0
fi

echo "The API now reports:"
curl -fsS -H "Authorization: Bearer $token" "$base/api/v1/system/inference" 2>/dev/null \
  | python3 -c 'import json, sys
snapshot = json.load(sys.stdin)
print("  configured:", snapshot.get("configured"))
print("  provider:  ", snapshot.get("configured_provider"))
for entry in snapshot.get("providers", []):
    print("  -", entry.get("provider"), "available:", entry.get("available"), entry.get("detail") or "")'
