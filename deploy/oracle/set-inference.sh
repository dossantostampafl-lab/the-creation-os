#!/usr/bin/env bash
# Points a running installation at a real inference provider, then restarts what reads the
# configuration and reports what the API itself now says.
#
#   sudo ./deploy/oracle/set-inference.sh              # anthropic, asks for the key
#   sudo ./deploy/oracle/set-inference.sh anthropic claude-sonnet-5
#   FALLBACK_PROVIDERS=anthropic sudo -E ./deploy/oracle/set-inference.sh freellmapi auto
#
# FALLBACK_PROVIDERS is the reserve order used only when the primary fails outright. Every provider
# in the chain must already be fully configured in .env, or the API would refuse to start, so the
# script checks that first and changes nothing when a reserve is missing its key or model.
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
  chatgpt) key_var=""; model_var=CHATGPT_MODEL; default_model=gpt-6.1-sol ;;
  anthropic) key_var=ANTHROPIC_API_KEY; model_var=ANTHROPIC_MODEL; default_model=claude-sonnet-5 ;;
  openai) key_var=LLM_API_KEY; model_var=LLM_MODEL; default_model=gpt-4o-mini ;;
  freellmapi) key_var=FREELLMAPI_API_KEY; model_var=FREELLMAPI_MODEL; default_model="" ;;
  openai_compatible) key_var=OPENAI_COMPATIBLE_API_KEY; model_var=OPENAI_COMPATIBLE_MODEL; default_model="" ;;
  *)
    echo "Unknown provider: $provider" >&2
    echo "Use one of: chatgpt, anthropic, openai, freellmapi, openai_compatible" >&2
    exit 1
    ;;
esac

model="${2:-$default_model}"
if [ -z "$model" ] && [ -t 0 ]; then
  read -rp "Model for $provider: " model
fi
if [ -z "$model" ]; then
  echo "A model is required." >&2
  exit 1
fi

# The deploy wrapper refreshes scripts before invoking this command. ChatGPT activation
# must fast-forward the complete installation so code, Compose mounts, and UI are one revision.
if [ "$provider" = "chatgpt" ]; then
  target_ref="${REF:-main}"
  if ! [[ "$target_ref" =~ ^[A-Za-z0-9._/-]+$ ]]; then
    echo "Invalid deployment ref: $target_ref" >&2
    exit 1
  fi
  echo "Updating the installation to origin/$target_ref before activating ChatGPT..."
  git checkout HEAD -- deploy/oracle deploy/stf 2>/dev/null || true
  git fetch --prune origin
  git fetch origin "+$target_ref:refs/remotes/origin/$target_ref"
  git merge --ff-only "origin/$target_ref"
fi

# The key may arrive in the environment, which is how CI passes it; otherwise it is asked for.
# -s keeps the key off the screen; -r stops a backslash in it from being eaten.
api_key=""
if [ "$provider" = "chatgpt" ]; then
  echo "ChatGPT uses Sign in with ChatGPT OAuth credentials, not an API key."
else
  api_key="${!key_var:-}"
  if [ -n "$api_key" ]; then
    echo "Using the $key_var already in the environment."
  elif [ -t 0 ]; then
    if [ "$provider" = "freellmapi" ]; then
      read -rsp "Paste the $provider API key, or just press Enter if it has none: " api_key
    else
      read -rsp "Paste the $provider API key and press Enter: " api_key
    fi
    echo
  else
    api_key="$(env_get "$key_var")"
    if [ -n "$api_key" ]; then
      echo "Keeping the $key_var already in .env."
    fi
  fi
  if [ -z "$api_key" ] && [ "$provider" != "freellmapi" ]; then
    echo "No $key_var was given, and .env holds none; nothing changed." >&2
    exit 1
  fi
  if [ -z "$api_key" ]; then
    echo "No key: FreeLLMAPI will be called without an Authorization header."
  else
    printf 'Key received: %s characters.\n' "${#api_key}"
  fi
fi

# A key created for one Workspace already carries it, so this stays empty for almost everyone.
# It is only needed for a credential that can act on more than one Workspace, and the API
# rejects it when it does not match the key's Workspace. It is an identifier, not a secret,
# so it is read and shown normally.
workspace_id=""
if [ "$provider" = "anthropic" ]; then
  workspace_id="${ANTHROPIC_WORKSPACE_ID:-}"
  if [ -z "$workspace_id" ] && [ -t 0 ]; then
    read -rp "Workspace ID (press Enter to skip; only for a multi-Workspace key): " workspace_id
  fi
  workspace_id="$(printf '%s' "$workspace_id" | tr -d '[:space:]')"
  if [ -n "$workspace_id" ] && ! printf '%s' "$workspace_id" | grep -qE '^wrkspc_[A-Za-z0-9]+$'; then
    echo "That is not a Workspace ID. It looks like wrkspc_011CZkZaBF1tNoB5wlCeusgy." >&2
    echo "Nothing was changed." >&2
    exit 1
  fi
fi

# The reserve chain. An unset FALLBACK_PROVIDERS clears any earlier chain, so switching back to a single
# provider does not leave a stale reserve behind.
fallback="$(printf '%s' "${FALLBACK_PROVIDERS:-}" | tr -d '[:space:]')"
if [ "$provider" = "chatgpt" ] && [ -n "$fallback" ]; then
  echo "ChatGPT plan requests never switch to another provider or billing path; clearing the requested reserve chain."
  fallback=""
fi
if [ -n "$fallback" ]; then
  IFS=',' read -ra reserves <<< "$fallback"
  for reserve in "${reserves[@]}"; do
    case "$reserve" in
      chatgpt)
        echo "ChatGPT plan usage cannot be a reserve provider. Configure chatgpt as the primary so plan usage is explicit." >&2
        echo "Nothing was changed." >&2
        exit 1
        ;;
      anthropic) reserve_key=ANTHROPIC_API_KEY; reserve_model=ANTHROPIC_MODEL ;;
      openai) reserve_key=LLM_API_KEY; reserve_model=LLM_MODEL ;;
      freellmapi) reserve_key=""; reserve_model=FREELLMAPI_MODEL ;;
      openai_compatible) reserve_key=""; reserve_model=OPENAI_COMPATIBLE_MODEL ;;
      *)
        echo "Unknown or unsupported reserve provider: '$reserve' (fake is never allowed)." >&2
        echo "Nothing was changed." >&2
        exit 1
        ;;
    esac
    if [ "$reserve" = "$provider" ]; then
      echo "The reserve chain must not repeat the primary provider ($provider). Nothing was changed." >&2
      exit 1
    fi
    if [ -n "$reserve_key" ] && [ -z "$(env_get "$reserve_key")" ]; then
      echo "The reserve provider $reserve has no $reserve_key in .env, so the API could not start with it in the chain." >&2
      echo "Nothing was changed." >&2
      exit 1
    fi
    if [ -z "$(env_get "$reserve_model")" ]; then
      echo "The reserve provider $reserve has no $reserve_model in .env, so the API could not start with it in the chain." >&2
      echo "Nothing was changed." >&2
      exit 1
    fi
  done
fi

# FreeLLMAPI runs outside this stack, on this server. Its address is an identifier, not a secret.
freellmapi_url=""
if [ "$provider" = "freellmapi" ]; then
  freellmapi_url="${FREELLMAPI_BASE_URL:-$(env_get FREELLMAPI_BASE_URL)}"
  freellmapi_url="${freellmapi_url:-http://host.docker.internal:3001/v1}"
  if ! printf '%s' "$freellmapi_url" | grep -qE '^https?://[A-Za-z0-9._:/-]+$'; then
    echo "FREELLMAPI_BASE_URL must be an http(s) address without spaces or credentials. Nothing was changed." >&2
    exit 1
  fi
fi

cp .env .env.bak
chmod 600 .env.bak
env_set LLM_PROVIDER "$provider"
env_set "$model_var" "$model"
if [ -n "$key_var" ]; then
  env_set "$key_var" "$api_key"
fi
unset api_key
if [ "$provider" = "chatgpt" ]; then
  env_set CHATGPT_CREDENTIALS_FILE "/var/lib/creation/chatgpt/credentials.json"
  # Selecting ChatGPT while autonomous discovery/competition is already enabled is the
  # explicit operational action that authorizes those existing background jobs to use the
  # ChatGPT plan. Persist that consent so Settings can fail closed in every other path.
  if [ "$(env_get DEUS_AUTONOMY_DISCOVERY_ENABLED)" = "true" ] \
     || [ "$(env_get DEUS_AUTONOMY_COMPETITION_ENABLED)" = "true" ]; then
    env_set CHATGPT_BACKGROUND_AUTOMATION_CONSENT "true"
  fi
fi
env_set DEUS_VOICE_PRIMARY_PROVIDER "$provider"
if [ "$provider" = "anthropic" ]; then
  env_set ANTHROPIC_WORKSPACE_ID "$workspace_id"
fi
if [ "$provider" = "freellmapi" ]; then
  env_set FREELLMAPI_BASE_URL "$freellmapi_url"
fi
env_set LLM_FALLBACK_PROVIDERS "$fallback"
chmod 600 .env

echo "Written to .env (the previous file is kept as .env.bak):"
printf '  LLM_PROVIDER=%s\n' "$(env_get LLM_PROVIDER)"
printf '  %s=%s\n' "$model_var" "$(env_get "$model_var")"
if [ "$provider" = "anthropic" ] && [ -n "$(env_get ANTHROPIC_WORKSPACE_ID)" ]; then
  printf '  ANTHROPIC_WORKSPACE_ID=%s\n' "$(env_get ANTHROPIC_WORKSPACE_ID)"
fi
printf '  LLM_FALLBACK_PROVIDERS=%s\n' "$(env_get LLM_FALLBACK_PROVIDERS)"
if [ "$provider" = "freellmapi" ]; then
  printf '  FREELLMAPI_BASE_URL=%s\n' "$(env_get FREELLMAPI_BASE_URL)"
fi
if [ "$provider" = "chatgpt" ]; then
  printf '  CHATGPT_CREDENTIALS_FILE=%s\n' "$(env_get CHATGPT_CREDENTIALS_FILE)"
elif [ -n "$(env_get "$key_var")" ]; then
  printf '  %s=<set>\n' "$key_var"
elif [ "$provider" = "freellmapi" ]; then
  printf '  %s=<none: no Authorization header is sent>\n' "$key_var"
else
  echo "The key was not written. .env.bak still holds the previous file." >&2
  exit 1
fi

# The containers read .env only when they are created. ChatGPT activation also upgrades
# the complete runtime so frontend, API, workers and credential-volume mounts are one revision.
echo
profile_args=()
if grep -qE "^DEUS_(CONTEXT_RETRIEVAL|DIAGNOSTICS|AUTONOMY_DISCOVERY|AUTONOMY_COMPETITION)_ENABLED=true$" .env; then
  profile_args+=(--profile connected-deus)
fi
if grep -q "^STF_AUTO_TRAINING_ENABLED=true$" .env; then
  profile_args+=(--profile security-task-force)
fi
if grep -q "^TELEMETRY_ENABLED=true$" .env; then
  profile_args+=(--profile observability)
fi
echo "Building and recreating the current runtime..."
"${COMPOSE[@]}" "${profile_args[@]}" up -d --build --remove-orphans

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

if ! curl -fsS "$base/api/v1/health/ready" >/dev/null 2>&1; then
  echo "The API did not become ready after the inference change." >&2
  "${COMPOSE[@]}" ps api worker >&2 || true
  exit 1
fi

if [ "$provider" = "chatgpt" ]; then
  echo
  echo "Preparing the stable Oracle host identity required for ChatGPT authorization..."
  "$REPO_DIR/deploy/oracle/chatgpt-host-id.sh"
fi

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

if [ "$provider" = "chatgpt" ]; then
  echo
  echo "Running the authentication-ready smoke test..."
  "$REPO_DIR/deploy/oracle/smoke-test.sh" --deus
fi
