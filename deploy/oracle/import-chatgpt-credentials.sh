#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/chatgpt-credentials.json" >&2
  exit 2
fi

source_file="$1"
if [ ! -f "$source_file" ]; then
  echo "Credential file not found." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)

python3 - "$source_file" <<'PY'
import json, os, stat, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
required = {"client_id", "access_token", "refresh_token", "id_token", "subject", "saved_at"}
missing = sorted(name for name in required if not data.get(name))
if data.get("issuer") != "https://auth.openai.com":
    missing.append("issuer:https://auth.openai.com")
if data.get("client_id") == "dynamic_agent_client":
    missing.append("issued_client_id")
try:
    if int(data.get("expires_in", 0)) <= 0:
        missing.append("expires_in")
except (TypeError, ValueError):
    missing.append("expires_in")
scope = data.get("scopes", data.get("scope", []))
if isinstance(scope, str):
    scopes = set(scope.split())
else:
    scopes = {str(item) for item in scope}
if "chatgpt.tokens.use.direct" not in scopes:
    missing.append("scope:chatgpt.tokens.use.direct")
if missing:
    raise SystemExit("Credential file is incomplete: " + ", ".join(missing))
mode = stat.S_IMODE(os.stat(path).st_mode)
if mode & 0o077:
    print("warning: source credential file is readable by group/others", file=sys.stderr)
print("Credential structure validated; token values were not printed.")
PY

api_container="$("${COMPOSE[@]}" ps -q api)"
worker_container="$("${COMPOSE[@]}" ps -q worker)"
if [ -z "$api_container" ] || [ -z "$worker_container" ]; then
  echo "The API and worker containers must both be running. Deploy/rebuild the ChatGPT-capable stack first." >&2
  exit 1
fi

credential_mount() {
  docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/creation/chatgpt"}}{{.Name}}{{end}}{{end}}' "$1" 2>/dev/null
}
api_mount="$(credential_mount "$api_container")"
worker_mount="$(credential_mount "$worker_container")"
if [ -z "$api_mount" ] || [ -z "$worker_mount" ]; then
  echo "The protected ChatGPT credential volume is not mounted in API and worker. Deploy/rebuild before importing OAuth credentials." >&2
  exit 1
fi
if [ "$api_mount" != "$worker_mount" ]; then
  echo "API and worker do not share the same ChatGPT credential volume; refusing a partial credential install." >&2
  exit 1
fi
echo "Protected ChatGPT credential volume verified for API and worker."

host_id="$("${COMPOSE[@]}" exec -T api python - <<'PY'
from pathlib import Path
import uuid
root = Path("/var/lib/creation/chatgpt")
root.mkdir(parents=True, exist_ok=True)
path = root / "host-id"
if path.exists():
    value = path.read_text(encoding="utf-8").strip()
else:
    value = "urn:uuid:" + str(uuid.uuid4())
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
print(value)
PY
)"

temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
python3 - "$source_file" "$temporary" "$host_id" <<'PY'
import json, os, sys
source, target, host_id = sys.argv[1:]
with open(source, "r", encoding="utf-8") as handle:
    data = json.load(handle)
# The OAuth session may have been created on the browser/laptop host. OpenAI's
# self-hosted VM flow requires the imported runtime record to preserve the VM's
# already-persisted host ID rather than copying the laptop host ID over it.
data["ext_agent_host_id"] = host_id
with open(target, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
os.chmod(target, 0o600)
PY

"${COMPOSE[@]}" exec -T api sh -c '
  set -eu
  umask 077
  mkdir -p /var/lib/creation/chatgpt
  temp=/var/lib/creation/chatgpt/credentials.json.tmp
  cat > "$temp"
  chmod 600 "$temp"
  mv "$temp" /var/lib/creation/chatgpt/credentials.json
' < "$temporary"

"${COMPOSE[@]}" exec -T api python - <<'PY'
from app.config import settings
from app.inference.chatgpt_credentials import ChatGPTCredentialStore
store = ChatGPTCredentialStore(settings.chatgpt_credentials_file)
record = store._read()
print("ChatGPT OAuth credential loaded for client:", record.client_id)
print("Plan usage scope:", "enabled" if "chatgpt.tokens.use.direct" in record.scopes else "disabled")
PY

echo "ChatGPT credentials are installed in the protected shared volume."
echo "No access token or refresh token was printed."
