#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/compose.yml"

docker compose -f "$COMPOSE" --profile cyber-range up -d --build
"$ROOT/scripts/verify.sh"
