#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/compose.yml"

if curl --fail --silent --show-error -X POST http://127.0.0.1:7070/reset >/dev/null 2>&1; then
  echo "Range Controller state reset."
else
  echo "Range Controller was not reachable; removing disposable Docker state directly."
fi

docker compose -f "$COMPOSE" --profile cyber-range down -v --remove-orphans
