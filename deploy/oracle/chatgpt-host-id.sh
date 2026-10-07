#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

api_container="$("${COMPOSE[@]}" ps -q api)"
if [ -z "$api_container" ]; then
  echo "The API container must be running before preparing the ChatGPT host identity." >&2
  exit 1
fi

"${COMPOSE[@]}" exec -T api python - <<'PY'
from pathlib import Path
import uuid

root = Path("/var/lib/creation/chatgpt")
root.mkdir(parents=True, exist_ok=True)
try:
    root.chmod(0o700)
except OSError:
    pass
path = root / "host-id"
if path.exists():
    value = path.read_text(encoding="utf-8").strip()
else:
    value = "urn:uuid:" + str(uuid.uuid4())
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
if not value.startswith("urn:uuid:"):
    raise SystemExit("Stored ChatGPT host ID has an unsupported format")
print(value)
PY
