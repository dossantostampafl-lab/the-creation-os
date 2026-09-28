#!/usr/bin/env bash
# The last lines of the api and worker logs, for reading a failure that only shows up in use.
#
#   sudo ./deploy/oracle/show-logs.sh [lines]
#
# It follows the running containers rather than this directory, for the same reason
# check-inference.sh does: the server can carry more than one checkout.
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

lines="${1:-120}"
case "$lines" in
  ''|*[!0-9]*) echo "The line count must be a number." >&2; exit 1 ;;
esac
[ "$lines" -gt 500 ] && lines=500

for service in api worker; do
  container="$(docker ps --filter "label=com.docker.compose.service=$service" --format '{{.ID}}' | head -1)"
  echo "== $service =="
  if [ -z "$container" ]; then
    echo "   No $service container is running."
    continue
  fi
  # A log line can carry whatever an error put in it, so anything that looks like a key is
  # replaced before it reaches a workflow log that others can read.
  docker logs --tail "$lines" "$container" 2>&1 \
    | python3 -c '
import re
import sys

SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|wrkspc_[A-Za-z0-9]+|Bearer\s+[A-Za-z0-9._\-]{8,})")
for line in sys.stdin:
    sys.stdout.write("   " + SECRET.sub("<redacted>", line))
'
  echo
done
