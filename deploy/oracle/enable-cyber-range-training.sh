#!/usr/bin/env bash
# Starts the isolated Cyber Range, its private relay and the automatic STF training loop.
# No vulnerable target is published beyond host loopback and all automatic missions remain
# bound to cyber_range:* with real:* explicitly excluded by the training contracts.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/deploy/oracle/env-file.sh"
[ -f .env ] || { echo "Run install.sh first." >&2; exit 1; }
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

token="$(env_get CYBER_RANGE_CONTROL_TOKEN)"
if ! [[ "$token" =~ ^[A-Za-z0-9._-]{32,}$ ]]; then
  token="$(openssl rand -hex 32)"
fi
signing_key="$(env_get STF_GATEWAY_SIGNING_KEY)"
if [ "${#signing_key}" -lt 32 ]; then
  signing_key="$(openssl rand -hex 32)"
fi

env_set CYBER_RANGE_CONTROL_TOKEN "$token"
env_set CYBER_RANGE_CONTROL_ADDR "host.docker.internal:7071"
env_set CYBER_RANGE_CONTROLLER_URL "http://host.docker.internal:7071"
env_set STF_GATEWAY_SIGNING_KEY "$signing_key"
env_set STF_ALLOWED_ENVIRONMENTS "cyber_range:"
env_set STF_AUTO_TRAINING_ENABLED "true"
env_set STF_AUTO_TRAINING_CYCLE_SECONDS "${STF_AUTO_TRAINING_CYCLE_SECONDS:-60}"
chmod 600 .env

echo "== Starting isolated Cyber Range =="
./cyber_range/scripts/start.sh

docker_host_ip="$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)"
if [ -z "$docker_host_ip" ]; then
  echo "Could not determine the private Docker host gateway for the Cyber Range relay." >&2
  exit 1
fi
python3 - "$docker_host_ip" <<'PY'
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
if not address.is_private:
    raise SystemExit("Docker host gateway is not private")
PY

relay_user="tco-range-relay"
if ! id "$relay_user" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$relay_user"
fi
install -d -m 700 /etc/the-creation-os
printf 'CYBER_RANGE_CONTROL_TOKEN=%s\n' "$token" > /etc/the-creation-os/cyber-range.env
chmod 600 /etc/the-creation-os/cyber-range.env

cat > /etc/systemd/system/the-creation-cyber-range-relay.service <<EOF
[Unit]
Description=THE CREATION OS private Cyber Range control relay
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
User=$relay_user
Group=$relay_user
EnvironmentFile=/etc/the-creation-os/cyber-range.env
ExecStart=/usr/bin/python3 $REPO_DIR/cyber_range/control_relay.py --bind $docker_host_ip --port 7071
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6
LockPersonality=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now the-creation-cyber-range-relay.service

# Oracle's host INPUT chain rejects unsolicited traffic. Permit only Docker-originated
# traffic to the private authenticated relay; the service itself is bound to a private IP.
if ! iptables -C INPUT -s 172.16.0.0/12 -p tcp --dport 7071 -j ACCEPT 2>/dev/null; then
  reject_line="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')"
  if [ -n "$reject_line" ]; then
    iptables -I INPUT "$reject_line" -s 172.16.0.0/12 -p tcp --dport 7071 -j ACCEPT
  else
    iptables -A INPUT -s 172.16.0.0/12 -p tcp --dport 7071 -j ACCEPT
  fi
fi

for _ in $(seq 1 30); do
  if curl -fsS -H "Authorization: Bearer $token" "http://$docker_host_ip:7071/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS -H "Authorization: Bearer $token" "http://$docker_host_ip:7071/health" >/dev/null

echo "== Starting STF control plane and automatic training worker =="
"${COMPOSE[@]}" --profile security-task-force up -d --build stf-nats stf-opa stf-temporal
"${COMPOSE[@]}" --profile security-task-force up -d --build --force-recreate api stf-worker stf-gateway stf-training-worker

for _ in $(seq 1 45); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null 2>&1; then
    training="$(docker ps --filter 'label=com.docker.compose.service=stf-training-worker' --filter status=running -q)"
    stf_worker="$(docker ps --filter 'label=com.docker.compose.service=stf-worker' --filter status=running -q)"
    gateway="$(docker ps --filter 'label=com.docker.compose.service=stf-gateway' --filter status=running -q)"
    if [ -n "$training" ] && [ -n "$stf_worker" ] && [ -n "$gateway" ]; then
      break
    fi
  fi
  sleep 2
done

docker ps --filter 'label=com.docker.compose.service=stf-training-worker' --filter status=running -q | grep -q .
docker ps --filter 'label=com.docker.compose.service=stf-worker' --filter status=running -q | grep -q .
docker ps --filter 'label=com.docker.compose.service=stf-gateway' --filter status=running -q | grep -q .

echo "Cyber Range and automatic STF training are active."
