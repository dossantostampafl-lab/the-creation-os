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

for service in api worker stf-temporal stf-worker stf-training-worker stf-gateway; do
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

# State summaries contain no conversation text, credentials, or outbox payloads.
# Reachability alone cannot show whether a queued campaign actually executes.
api="$(docker ps --filter 'label=com.docker.compose.service=api' --format '{{.ID}}' | head -1)"
if [ -n "$api" ]; then
  echo '== Runtime execution state (read-only) =='
  docker exec -i "$api" python - <<'PY'
import asyncio
import json
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        await session.execute(text('SET TRANSACTION READ ONLY'))
        for table, column in [('stf_runs', 'state'), ('stf_outbox', 'status'),
                              ('stf_dispatches', 'status'), ('missions', 'status'), ('tasks', 'status')]:
            rows = await session.execute(text(f'SELECT {column}, count(*) FROM {table} GROUP BY {column}'))
            print(table, json.dumps(dict(rows.all())))
        rows = await session.execute(text("SELECT state, desired_state, extract(epoch from (now()-created_at))::int AS age_seconds, extract(epoch from (now()-updated_at))::int AS unchanged_seconds FROM stf_runs WHERE state NOT IN ('COMPLETED','ABORTED') ORDER BY created_at LIMIT 10"))
        print('unfinished_training', json.dumps([dict(row._mapping) for row in rows]))
        rows = await session.execute(text("SELECT destination, status, max(attempts) AS max_attempts, count(*) FROM stf_outbox GROUP BY destination, status"))
        print('outbox_delivery', json.dumps([dict(row._mapping) for row in rows]))

asyncio.run(main())
PY
fi
