#!/usr/bin/env bash
# Installs and starts THE CREATION OS on a fresh Ubuntu server (made for the Oracle Cloud
# "Always Free" VM, ARM or x86). Safe to run again: it updates and restarts, keeping data and secrets.
#
#   sudo ./deploy/oracle/install.sh
#
# Optional: CREATION_DOMAIN=my-name.duckdns.org sudo -E ./deploy/oracle/install.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

log() { printf '\n==> %s\n' "$*"; }

env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

env_set() {
  if grep -qE "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

log "Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  usermod -aG docker "$SUDO_USER" || true
fi

log "Memory"
# Building the images needs more than the 1 GB of the smallest free VMs.
mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
if [ "$mem_kb" -lt 4000000 ] && ! swapon --show | grep -q .; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "Added 4 GB of swap."
fi

log "Firewall (ports 80 and 443; FreeLLMAPI only for the containers)"
# Oracle's Ubuntu images reject everything but SSH in iptables, on top of the cloud security list.
for port in 80 443; do
  if ! iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    reject_line=$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')
    if [ -n "$reject_line" ]; then
      iptables -I INPUT "$reject_line" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
    else
      iptables -A INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT
    fi
  fi
done
# A FreeLLMAPI running on this server (port 3001) must be reachable from the containers
# (host.docker.internal), but only from the Docker networks, never from the internet.
if ! iptables -C INPUT -s 172.16.0.0/12 -p tcp --dport 3001 -j ACCEPT 2>/dev/null; then
  reject_line=$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')
  if [ -n "$reject_line" ]; then
    iptables -I INPUT "$reject_line" -s 172.16.0.0/12 -p tcp --dport 3001 -j ACCEPT
  fi
fi
if command -v netfilter-persistent >/dev/null 2>&1; then
  netfilter-persistent save >/dev/null 2>&1 || true
fi

log "Configuration (.env)"
first_install=false
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  first_install=true
fi
if [ "$(env_get APP_SECRET_KEY)" = "replace-me-with-a-secure-random-value" ] || [ -z "$(env_get APP_SECRET_KEY)" ]; then
  env_set APP_SECRET_KEY "$(openssl rand -hex 32)"
fi
if [ "$(env_get CREATOR_BOOTSTRAP_PASSWORD)" = "change-me-securely" ] || [ -z "$(env_get CREATOR_BOOTSTRAP_PASSWORD)" ]; then
  env_set CREATOR_BOOTSTRAP_PASSWORD "$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
fi
# Production mode: only the configured Creator credentials can claim the empty system.
env_set APP_ENV production

domain="${CREATION_DOMAIN:-$(env_get CREATION_DOMAIN)}"
if [ -z "$domain" ]; then
  public_ip=$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me)
  domain="${public_ip//./-}.sslip.io"
fi
env_set CREATION_DOMAIN "$domain"
env_set CORS_ALLOW_ORIGINS "https://$domain"

log "Build and start (the first build takes a few minutes)"
"${COMPOSE[@]}" up -d --build --remove-orphans

log "Waiting for the API"
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null

log "Creator account"
username=$(env_get CREATOR_BOOTSTRAP_USERNAME)
password=$(env_get CREATOR_BOOTSTRAP_PASSWORD)
body=$(printf '{"username":"%s","password":"%s"}' "$username" "$password")
response=$(curl -sS -o /tmp/tco-bootstrap.json -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -d "$body" http://127.0.0.1:8000/api/v1/auth/bootstrap)
if [ "$response" = "201" ]; then
  creator_id=$(python3 -c 'import json; print(json.load(open("/tmp/tco-bootstrap.json"))["id"])')
  env_set SOVEREIGN_CREATOR_ID "$creator_id"
  # Pin the sovereign Creator so no other account can ever act, then reload the settings.
  "${COMPOSE[@]}" up -d --force-recreate api worker
  echo "Creator created."
elif [ "$response" = "409" ]; then
  echo "Creator already exists."
else
  echo "Creator bootstrap answered HTTP $response:" >&2
  cat /tmp/tco-bootstrap.json >&2
fi
rm -f /tmp/tco-bootstrap.json

provider=$(env_get LLM_PROVIDER)
cat <<EOF

========================================================================
 THE CREATION OS is online:  https://$domain
   (the HTTPS certificate can take a minute on the first start)

 Login   user: $username
         password: $password
 The password is in $REPO_DIR/.env (CREATOR_BOOTSTRAP_PASSWORD).
EOF
if [ "$first_install" = true ] || [ "$provider" = "fake" ] || [ -z "$provider" ]; then
  cat <<EOF

 DEUS still needs a model. Edit the keys and run this script again:
   nano $REPO_DIR/.env        (LLM_PROVIDER, ANTHROPIC_*, FREELLMAPI_*, ELEVENLABS_*)
   sudo ./deploy/oracle/install.sh
EOF
fi
echo "========================================================================"
