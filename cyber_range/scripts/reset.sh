#!/usr/bin/env bash
# Clears the Range's disposable scenario state. The evidence journal and the snapshots are proof of what
# happened and are never removed here: `down -v` would delete every volume, so it is not used.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/compose.yml"

if curl --fail --silent --show-error -X POST http://127.0.0.1:7070/reset >/dev/null 2>&1; then
  echo "Range Controller state reset."
else
  echo "Range Controller was not reachable; removing only the disposable state volume directly."
fi

docker compose -f "$COMPOSE" --profile cyber-range down --remove-orphans
# Only the scenario state goes. It may not exist (never started, or already gone), which is fine.
docker volume rm creation-cyber-range_range_state >/dev/null 2>&1 || true
echo "Evidence and snapshots were preserved."
