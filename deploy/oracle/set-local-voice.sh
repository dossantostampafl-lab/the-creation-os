#!/usr/bin/env bash
# Install and validate local speech before switching the existing DEUS gateway.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/deploy/oracle/env-file.sh"
[ -f .env ] || { echo "Run install.sh first." >&2; exit 1; }
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)
# Keep the live API serving while downloading the reusable public model files.
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" run --rm --no-deps -e DEUS_LOCAL_VOICE_MODELS_DIR=/var/lib/creation/voice api python -m app.voice_session.prepare
"${COMPOSE[@]}" run --rm --no-deps -e DEUS_LOCAL_VOICE_MODELS_DIR=/var/lib/creation/voice api python -m app.voice_session.verify_local
cp .env .env.before-local-voice
chmod 600 .env.before-local-voice
env_set DEUS_VOICE_SESSION_ENABLED true
env_set DEUS_VOICE_PRIMARY_PROVIDER freellmapi
voice_models="${DEUS_VOICE_CONVERSATION_MODELS:-$(env_get DEUS_VOICE_CONVERSATION_MODELS)}"
env_set DEUS_VOICE_CONVERSATION_MODELS "$voice_models"
# The same chat remains free when a typed turn follows a voice turn.
env_set LLM_PROVIDER freellmapi
fallback="$(env_get LLM_FALLBACK_PROVIDERS)"
# freellmapi is now the primary; Settings rejects a reserve chain that repeats LLM_PROVIDER.
fallback="$(printf '%s' "$fallback" | awk -v RS=',' '{
  gsub(/^[[:space:]]+|[[:space:]]+$/, ""); name = tolower($0)
  if (name != "" && name != "freellmapi" && !seen[name]++) out = out (out == "" ? "" : ",") name
} END { print out }')"
if [ -z "$fallback" ] && [ -n "$(env_get ANTHROPIC_API_KEY)" ] && [ -n "$(env_get ANTHROPIC_MODEL)" ]; then
  fallback="anthropic"
fi
env_set LLM_FALLBACK_PROVIDERS "$fallback"
env_set DEUS_LOCAL_VOICE_MODELS_DIR /var/lib/creation/voice
env_set DEUS_LOCAL_VOICE_SILENCE_MS 400
env_set DEUS_LOCAL_VOICE_CPU_THREADS 2
chmod 600 .env
"${COMPOSE[@]}" up -d --no-deps --force-recreate api
for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null; then
    echo "DEUS local voice is ready: Kokoro pm_santa, Vosk Portuguese, FreeLLMAPI."
    printf "FreeLLM voice model pool: %s\\n" "${voice_models:-<legacy FREELLMAPI_MODEL>}"
    printf "Inference reserve: %s\\n" "${fallback:-<none configured>}"
    exit 0
  fi
  sleep 2
done
echo "Local voice API did not become ready; restoring the previous environment." >&2
cp .env.before-local-voice .env
"${COMPOSE[@]}" up -d --no-deps --force-recreate api
exit 1
