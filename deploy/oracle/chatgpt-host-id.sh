#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

# The stable host ID belongs to the Oracle runtime and must live in the same protected
# named volume as the OAuth credentials. Use the long-running API container because the
# cloud profile makes its root filesystem read-only while keeping named volumes writable.
api_container="$("${COMPOSE[@]}" ps -q api | head -1)"
if [ -z "$api_container" ]; then
  echo "The API container is not running. Start/recreate the ChatGPT-capable API before preparing its host ID." >&2
  exit 1
fi

mount_name="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/creation/chatgpt"}}{{.Name}}{{end}}{{end}}' "$api_container" 2>/dev/null || true)"
if [ -z "$mount_name" ]; then
  echo "The running API does not have the protected ChatGPT credential volume mounted." >&2
  exit 1
fi

docker exec -i "$api_container" python - <<'PY'
from pathlib import Path
import uuid

root = Path("/var/lib/creation/chatgpt")
if not root.exists():
    raise SystemExit("ChatGPT credential volume mount is missing")
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
if not (
    value.startswith("urn:uuid:")
    or value.startswith("urn:ietf:params:oauth:jwk-thumbprint:")
    or value.startswith("did:key:")
):
    raise SystemExit("Stored ChatGPT host ID has an unsupported format")
print(value)
PY
