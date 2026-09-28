#!/usr/bin/env bash
# Gives DEUS its ElevenLabs voice, and proves ElevenLabs accepts the key and the voice.
#
#   sudo ELEVENLABS_API_KEY=... ELEVENLABS_VOICE_ID=... ./deploy/oracle/set-voice.sh
#   sudo ./deploy/oracle/set-voice.sh                    # asks for both
#
# Without this, the API answers 501 and the interface falls back to the browser's own speech
# synthesis for the rest of the session -- which is what "the voice is wrong" sounds like.
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
  echo "There is no .env in $REPO_DIR. Run deploy/oracle/install.sh first." >&2
  exit 1
fi

api_key="${ELEVENLABS_API_KEY:-}"
if [ -z "$api_key" ]; then
  if [ -t 0 ]; then
    read -rsp "Paste the ElevenLabs API key and press Enter: " api_key
    echo
  else
    # Changing only the voice must not require the key to travel again.
    api_key="$(env_get ELEVENLABS_API_KEY)"
    [ -n "$api_key" ] && echo "Keeping the ELEVENLABS_API_KEY already in .env."
  fi
fi
if [ -z "$api_key" ]; then
  echo "No ELEVENLABS_API_KEY was given, and .env holds none; nothing changed." >&2
  exit 1
fi
printf 'Key received: %s characters.\n' "${#api_key}"

voice_id="${ELEVENLABS_VOICE_ID:-}"
if [ -z "$voice_id" ] && [ -t 0 ]; then
  read -rp "Voice ID: " voice_id
fi
voice_id="$(printf '%s' "$voice_id" | tr -d '[:space:]')"
# An ElevenLabs voice id is 20 alphanumeric characters. The value ends up in a URL path, so a
# value that is not one is refused rather than sent.
if ! printf '%s' "$voice_id" | grep -qE '^[A-Za-z0-9]{20}$'; then
  echo "That is not a voice ID. It looks like I72ABy73veEFwPllwlHI (20 letters and digits)." >&2
  echo "Nothing changed." >&2
  exit 1
fi

model_id="${ELEVENLABS_MODEL_ID:-$(env_get ELEVENLABS_MODEL_ID)}"
model_id="${model_id:-eleven_flash_v2_5}"

cp .env .env.bak
chmod 600 .env.bak
env_set ELEVENLABS_ENABLED true
env_set ELEVENLABS_API_KEY "$api_key"
env_set ELEVENLABS_VOICE_ID "$voice_id"
env_set ELEVENLABS_MODEL_ID "$model_id"
env_set ELEVENLABS_STT_MODEL_ID "${ELEVENLABS_STT_MODEL_ID:-scribe_v2}"
unset api_key
chmod 600 .env

echo "Written to .env (the previous file is kept as .env.bak):"
printf '  ELEVENLABS_ENABLED=%s\n' "$(env_get ELEVENLABS_ENABLED)"
printf '  ELEVENLABS_VOICE_ID=%s\n' "$(env_get ELEVENLABS_VOICE_ID)"
printf '  ELEVENLABS_MODEL_ID=%s\n' "$(env_get ELEVENLABS_MODEL_ID)"
printf '  ELEVENLABS_STT_MODEL_ID=%s\n' "$(env_get ELEVENLABS_STT_MODEL_ID)"
printf '  ELEVENLABS_API_KEY=%s\n' "$([ -n "$(env_get ELEVENLABS_API_KEY)" ] && echo '<set>' || echo '<empty>')"

echo
echo "Restarting api and worker..."
"${COMPOSE[@]}" up -d --force-recreate api worker
sleep 15

# Ask ElevenLabs directly, from inside the container that holds the credential. A key that is
# valid for the account but cannot reach this voice answers here, not in a browser at midnight.
echo
echo "== What ElevenLabs itself says =="
container="$(docker ps --filter 'label=com.docker.compose.service=api' --format '{{.ID}}' | head -1)"
if [ -z "$container" ]; then
  echo "   No api container to ask from." >&2
  exit 1
fi
docker exec -i "$container" python -c '
import os

import httpx

key = os.getenv("ELEVENLABS_API_KEY", "")
voice = os.getenv("ELEVENLABS_VOICE_ID", "")
model = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")
headers = {"xi-api-key": key}

# The name is nice to have, and needs the voices_read permission a key may not carry. It is
# asked for first and its refusal is reported, never fatal: the app never calls this endpoint.
try:
    named = httpx.get(f"https://api.elevenlabs.io/v1/voices/{voice}", headers=headers, timeout=20)
    if named.status_code == 200:
        print("   Voice:", named.json().get("name", "<unnamed>"))
    elif named.status_code == 401:
        print("   (the key cannot read voice names; that permission is not needed to speak)")
    else:
        print(f"   (could not read the voice name: HTTP {named.status_code})")
except Exception as exc:
    print(f"   (could not read the voice name: {type(exc).__name__})")

# This is the call the application makes, so this is the one that has to work. Two words keep
# it to a few credits.
try:
    spoken = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers=headers,
        json={"text": "Estou aqui.", "model_id": model},
        timeout=40,
    )
except Exception as exc:
    raise SystemExit(f"   The request never arrived: {type(exc).__name__}: {exc}")

print(f"   Speaking: HTTP {spoken.status_code}")
if spoken.status_code == 200:
    print("  ", len(spoken.content), "bytes of", spoken.headers.get("content-type", "audio"))
else:
    print("   " + spoken.text[:300])
    raise SystemExit(1)
'
