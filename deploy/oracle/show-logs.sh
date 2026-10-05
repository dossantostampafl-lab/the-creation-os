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

for service in discovery-worker opportunity-worker api worker stf-temporal stf-worker stf-training-worker stf-gateway; do
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

echo '== MinIO inventory (read-only) =='
docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' | awk 'tolower($0) ~ /minio/ {print}'
gateway="$(docker ps --filter 'label=com.docker.compose.service=stf-gateway' --format '{{.ID}}' | head -1)"
if [ -n "$gateway" ]; then
  echo '== Gateway private network routes =='
  docker exec "$gateway" cat /proc/net/route
  docker exec "$gateway" cat /etc/hosts | awk '/host.docker.internal/ {print}'
  docker inspect -f '{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{$net.IPAddress}}{{println}}{{end}}' "$gateway"
fi

# State summaries contain no conversation text, credentials, or outbox payloads.
# Reachability alone cannot show whether a queued campaign actually executes.
api="$(docker ps --filter 'label=com.docker.compose.service=api' --format '{{.ID}}' | head -1)"
temporal="$(docker ps --filter 'label=com.docker.compose.service=stf-temporal' --format '{{.ID}}' | head -1)"
if [ -n "$temporal" ]; then
  echo '== Temporal private listeners =='
  docker inspect -f '{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{$net.IPAddress}}{{println}}{{end}}' "$temporal"
  docker exec "$temporal" cat /proc/net/tcp | python3 -c '
import socket, struct, sys
for line in sys.stdin:
    fields = line.split()
    if len(fields) > 3 and fields[3] == "0A" and fields[1].endswith(":1C41"):
        print("Listening on", socket.inet_ntoa(struct.pack("<I", int(fields[1].split(":")[0], 16))), "port 7233")
'
fi
if [ -n "$api" ]; then
  echo '== Runtime execution state (read-only) =='
  docker exec -i "$api" python - <<'PY'
import asyncio
import json
import re
import socket
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def main():
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo('stf-temporal', 7233, type=socket.SOCK_STREAM)})
        for address in addresses:
            try:
                with socket.create_connection((address, 7233), timeout=3):
                    print('temporal_connection', address, 'reachable')
            except OSError as error:
                print('temporal_connection', address, type(error).__name__)
    except OSError as error:
        print('temporal_resolution', type(error).__name__)
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
        rows = await session.execute(text("SELECT status, reason_codes FROM stf_dispatches ORDER BY created_at DESC LIMIT 10"))
        print('dispatch_reasons', json.dumps([{'status': row.status, 'reasons': [code for code in (row.reason_codes or []) if isinstance(code,str) and re.fullmatch('[A-Za-z0-9_]{1,96}',code)]} for row in rows]))
        rows = await session.execute(text("SELECT sector, status, count(*) FROM opportunities WHERE EXISTS (SELECT 1 FROM json_array_elements_text(evidence_refs_json) ref WHERE ref LIKE 'public:https://news.google.com/%') GROUP BY sector,status"))
        print('public_opportunities', json.dumps([dict(row._mapping) for row in rows]))
        rows = await session.execute(text("SELECT o.sector, count(*) FROM opportunity_theses t JOIN opportunities o ON o.id=t.opportunity_id WHERE EXISTS (SELECT 1 FROM json_array_elements_text(o.evidence_refs_json) ref WHERE ref LIKE 'public:https://news.google.com/%') GROUP BY o.sector"))
        print('public_theses', json.dumps([dict(row._mapping) for row in rows]))
        rows = await session.execute(text("SELECT status, error_json->>'code' AS code, attempt_count FROM tasks WHERE status IN ('FAILED','BLOCKED') LIMIT 20"))
        print('task_failures', json.dumps([{'status': row.status, 'code': row.code if re.fullmatch('[A-Z0-9_]{1,96}', row.code or '') else 'UNCLASSIFIED', 'attempts': row.attempt_count} for row in rows]))

asyncio.run(main())
PY
fi
