#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
cd "$(dirname "$0")/../.."
source deploy/oracle/env-file.sh
[ -f .env ] || { echo 'Existing installation required.' >&2; exit 1; }
umask 077
mkdir -p .connected-backups
backup=".connected-backups/observability-$(date -u +%Y%m%dT%H%M%SZ).env"
cp .env "$backup"
# Preserve an existing Grafana login; no password enters logs or process arguments.
if [ -z "$(env_get STF_GRAFANA_ADMIN_PASSWORD)" ]; then
  env_set STF_GRAFANA_ADMIN_PASSWORD "$(python3 -c 'import secrets;print(secrets.token_hex(24))')"
fi
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)
[ -n "$(env_get STF_GRAFANA_PORT)" ] || env_set STF_GRAFANA_PORT 3300
# A dormant installation may still carry the old 3001 default used by FreeLLM.
# Preserve a running Grafana's port; relocate only an inactive, conflicting setting.
if [ -z "$("${COMPOSE[@]}" --profile observability ps -q stf-grafana)" ]; then
  selected_port="$(python3 - "$(env_get STF_GRAFANA_PORT)" <<'PYPORT'
import socket, sys
configured = int(sys.argv[1])
for candidate in [configured, *range(3300, 3310)]:
    try:
        with socket.socket() as connection:
            connection.bind(('127.0.0.1', candidate))
        print(candidate)
        break
    except OSError:
        continue
else:
    raise SystemExit('No free loopback port for Grafana')
PYPORT
)"
  if [ "$selected_port" != "$(env_get STF_GRAFANA_PORT)" ]; then
    echo "Inactive Grafana port is occupied; selecting loopback port $selected_port."
    env_set STF_GRAFANA_PORT "$selected_port"
  fi
fi
env_set TELEMETRY_ENABLED true
env_set TELEMETRY_OTLP_ENDPOINT http://otel-collector:4318
[ -n "$(env_get TELEMETRY_SAMPLE_RATIO)" ] || env_set TELEMETRY_SAMPLE_RATIO 1.0
profiles=(--profile observability)
if grep -qE '^DEUS_(CONTEXT_RETRIEVAL|DIAGNOSTICS|AUTONOMY_DISCOVERY|AUTONOMY_COMPETITION)_ENABLED=true$' .env; then
  profiles+=(--profile connected-deus)
fi
if grep -q '^STF_AUTO_TRAINING_ENABLED=true$' .env; then profiles+=(--profile security-task-force); fi
if ! "${COMPOSE[@]}" "${profiles[@]}" up -d --build --remove-orphans; then
  cp "$backup" .env
  "${COMPOSE[@]}" "${profiles[@]}" up -d --build || true
  exit 1
fi
# The check emits synthetic operational metadata, never a prompt or an audio sample.
trace="$("${COMPOSE[@]}" exec -T -e TELEMETRY_SAMPLE_RATIO=1.0 api python - <<'PY'
from app.observability.telemetry import configure_telemetry, operation
from opentelemetry import metrics, trace
import httpx, time
for attempt in range(45):
    try:
        response = httpx.get('http://127.0.0.1:8000/api/v1/health/ready', timeout=2)
        if response.is_success:
            break
    except httpx.HTTPError:
        pass
    if attempt == 44:
        raise RuntimeError('API readiness timeout; observability remains enabled for diagnosis')
    time.sleep(2)
assert configure_telemetry('verification')
with operation('verification.stack'):
    identifier = trace.get_current_span().get_span_context().trace_id
    httpx.get('http://127.0.0.1:8000/api/v1/auth/me', timeout=5)
assert trace.get_tracer_provider().force_flush(timeout_millis=3000)
metrics.get_meter_provider().force_flush(timeout_millis=3000)
print(format(identifier, '032x'))
PY
)"
printf '%s\n' "$(env_get STF_GRAFANA_ADMIN_PASSWORD)" | python3 deploy/oracle/verify-observability.py \
  --port "$(env_get STF_GRAFANA_PORT)" --trace "$trace"
echo 'Private observability enabled; Grafana remains on loopback. Use an SSH tunnel.'
