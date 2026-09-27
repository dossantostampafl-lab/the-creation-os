#!/usr/bin/env bash
# Gives the Creator a password you choose, and ends every session opened under the old one.
#
#   sudo ./deploy/oracle/set-creator-password.sh          # asks, without echoing
#   sudo CREATOR_PASSWORD=... ./deploy/oracle/set-creator-password.sh   # how CI passes it
#
# Rotating is three steps and all three have to happen: write the password into .env, recreate
# the API so it reads it, then run rotate-creator-password, which is what actually changes the
# stored hash. Doing only the first leaves .env and the database disagreeing -- the state this
# server was already in, and the reason a password that looked right did not work.
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

password="${CREATOR_PASSWORD:-}"
if [ -z "$password" ]; then
  if [ -t 0 ]; then
    read -rsp "New password for the Creator: " password
    echo
    read -rsp "Again, to be sure: " confirmation
    echo
    if [ "$password" != "$confirmation" ]; then
      echo "They do not match; nothing changed." >&2
      exit 1
    fi
    unset confirmation
  else
    echo "No CREATOR_PASSWORD in the environment and no terminal to ask at; nothing changed." >&2
    exit 1
  fi
fi

# This credential is the whole system's front door, on the public internet.
if [ "${#password}" -lt 12 ]; then
  echo "That is ${#password} characters. Use at least 12; nothing changed." >&2
  exit 1
fi
# bcrypt hashes the first 72 bytes and silently ignores the rest, so a longer password would
# not be the password it looks like. Bytes, not characters: an accent costs two.
byte_length="$(printf '%s' "$password" | wc -c)"
if [ "$byte_length" -gt 72 ]; then
  echo "That is $byte_length bytes, and bcrypt only reads the first 72; nothing changed." >&2
  exit 1
fi
# A bash match, not a grep: grep reads line by line, so a newline is the one control character
# it can never find inside a line -- and it is the one that matters, because the text after it
# becomes another line in .env, which Compose reads as another variable.
if [[ "$password" =~ [[:cntrl:]] ]]; then
  echo "The password contains a control character or a line break; nothing changed." >&2
  exit 1
fi
printf 'Password accepted: %s characters.\n' "${#password}"

cp .env .env.bak
chmod 600 .env.bak
env_set CREATOR_BOOTSTRAP_PASSWORD "$password"
chmod 600 .env

# The API reads .env when the container is created, and rotate-creator-password takes the
# password the running process holds -- so the restart has to come before the rotation.
echo "Recreating api and worker so they read the new value..."
"${COMPOSE[@]}" up -d --force-recreate api worker

port="$(env_get CREATION_API_PORT)"
base="http://127.0.0.1:${port:-8000}"
printf 'Waiting for the API'
for _ in $(seq 1 60); do
  if curl -fsS "$base/api/v1/health/ready" >/dev/null 2>&1; then
    break
  fi
  printf '.'
  sleep 2
done
echo

echo "Rotating..."
set +e
"${COMPOSE[@]}" exec -T api rotate-creator-password
status=$?
set -e

case "$status" in
  0) echo "Done. Every session opened under the old password is closed." ;;
  3)
    echo "The Creator already had this password, so nothing was rotated."
    echo "The .env now holds it too, which is what the API compares against."
    ;;
  2) echo "Refused: the password is longer than bcrypt reads." >&2; exit 1 ;;
  *)
    echo "The rotation refused; the reason is in the line above." >&2
    echo ".env.bak holds the previous file." >&2
    exit 1
    ;;
esac

# The rotation is only real if the new password opens a session. Ask the API, not the database.
username="$(env_get CREATOR_BOOTSTRAP_USERNAME)"
login_body="$(python3 -c 'import json, sys; print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))' \
  "$username" "$password")"
unset password
code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$base/api/v1/auth/login" \
  -H 'Content-Type: application/json' -d "$login_body" 2>/dev/null || echo "000")"
unset login_body

if [ "$code" = "200" ]; then
  echo "Verified: '$username' logs in with the new password."
else
  echo "The new password did not log in (HTTP $code). .env.bak holds the previous file." >&2
  exit 1
fi
