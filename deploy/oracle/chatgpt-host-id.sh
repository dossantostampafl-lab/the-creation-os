#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

# Use a one-shot container so host identity can be prepared even when the long-running
# API is stopped or waiting for OAuth-related configuration. The service image supplies
# the canonical protected volume mount, but the script imports only Python's stdlib.
"${COMPOSE[@]}" run --rm --no-deps --entrypoint python api - <<'PY'
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
if not (
    value.startswith("urn:uuid:")
    or value.startswith("urn:ietf:params:oauth:jwk-thumbprint:")
    or value.startswith("did:key:")
):
    raise SystemExit("Stored ChatGPT host ID has an unsupported format")
print(value)
PY
