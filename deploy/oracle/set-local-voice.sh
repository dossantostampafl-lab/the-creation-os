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
env_set DEUS_VOICE_ENGINE local
env_set DEUS_VOICE_SESSION_ENABLED true
env_set DEUS_VOICE_PRIMARY_PROVIDER freellmapi
# The same chat remains free when a typed turn follows a voice turn.
env_set LLM_PROVIDER freellmapi
env_set LLM_FALLBACK_PROVIDERS ""
env_set DEUS_LOCAL_VOICE_MODELS_DIR /var/lib/creation/voice
env_set DEUS_LOCAL_VOICE_SILENCE_MS 400
env_set ELEVENLABS_ENABLED false
chmod 600 .env
"${COMPOSE[@]}" up -d --no-deps --force-recreate api
for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null; then
    echo "DEUS local voice is ready: Kokoro pm_santa, Vosk Portuguese, FreeLLMAPI."
    exit 0
  fi
  sleep 2
done
echo "Local voice API did not become ready; restoring the previous environment." >&2
cp .env.before-local-voice .env
"${COMPOSE[@]}" up -d --no-deps --force-recreate api
exit 1
