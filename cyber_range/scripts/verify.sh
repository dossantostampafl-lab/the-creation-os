#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/compose.yml"

retry() {
  local url="$1"
  local attempts="${2:-60}"
  for ((i=1; i<=attempts; i++)); do
    if curl --fail --silent --show-error "$url" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "Verification failed: $url" >&2
  return 1
}

docker compose -f "$COMPOSE" --profile cyber-range config --quiet
retry http://127.0.0.1:7070/health
retry http://127.0.0.1:3000/
retry http://127.0.0.1:8080/WebGoat
retry http://127.0.0.1:9090/WebWolf

echo "Creation Cyber Range v1 verified on loopback-only endpoints."
