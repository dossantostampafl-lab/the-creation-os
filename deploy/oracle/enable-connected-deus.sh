#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p .connected-backups
"${COMPOSE[@]}" exec -T postgres pg_dump -U postgres the_creation_os | gzip > ".connected-backups/database-$stamp.sql.gz"
cp .env ".connected-backups/env-$stamp"
rollback() {
  cp ".connected-backups/env-$stamp" .env
  "${COMPOSE[@]}" --profile connected-deus stop knowledge-worker diagnostics-worker discovery-worker opportunity-worker || true
  "${COMPOSE[@]}" up -d --force-recreate api worker || true
  echo 'Activation failed; original flags restored. Private backups retained for diagnosis.' >&2
}
python3 - <<'PY'
from pathlib import Path
p=Path('.env')
lines=p.read_text().splitlines()
values={'DEUS_KNOWLEDGE_INGESTION_ENABLED':'true','DEUS_CONTEXT_RETRIEVAL_ENABLED':'true',
        'DEUS_DIAGNOSTICS_ENABLED':'true','DEUS_AUTONOMY_DISCOVERY_ENABLED':'true',
        'DEUS_AUTONOMY_COMPETITION_ENABLED':'true',
        'DEUS_OBSIDIAN_EXPORT_ENABLED':'true'}
existing={line.split('=',1)[0]:line.split('=',1)[1] for line in lines if '=' in line and not line.startswith('#')}
origins=[value.strip() for value in existing.get('CORS_ALLOW_ORIGINS','').strip('\"\'').split(',') if value.strip()]
for origin in ['https://localhost','capacitor://localhost']:
    if origin not in origins: origins.append(origin)
values['CORS_ALLOW_ORIGINS']=','.join(origins)
# A connected DEUS deployment must not silently lose its configured reserve.
# Preserve FreeLLMAPI as primary, but restore Anthropic when the server already
# has a valid Anthropic configuration and the fallback chain is accidentally empty.
primary=existing.get('LLM_PROVIDER','').strip('"\'').strip().lower()
fallbacks=existing.get('LLM_FALLBACK_PROVIDERS','').strip('"\'').strip()
anthropic_key=existing.get('ANTHROPIC_API_KEY','').strip('"\'').strip()
anthropic_model=existing.get('ANTHROPIC_MODEL','').strip('"\'').strip()
if primary == 'freellmapi' and not fallbacks and anthropic_key and anthropic_model:
    values['LLM_FALLBACK_PROVIDERS']='anthropic'
lines=[line for line in lines if not any(line.startswith(key+'=') for key in values)]
p.write_text('\n'.join(lines+[key+'='+value for key,value in values.items()])+'\n')
p.chmod(0o600)
PY
# Migration is additive. Backfill imports Creator messages only; model assertions without
# provenance never become durable evidence. No database downgrade on runtime failures.
if ! "${COMPOSE[@]}" --profile connected-deus up -d --build api worker knowledge-worker diagnostics-worker discovery-worker opportunity-worker; then
  rollback
  exit 1
fi
for attempt in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/health/ready',timeout=3)" >/dev/null 2>&1; then
    if ! "${COMPOSE[@]}" exec -T api python -m app.knowledge.backfill --apply; then
      rollback
      exit 1
    fi
    echo 'Connected DEUS enabled; no external action authority was added.'
    exit 0
  fi
  sleep 2
done
rollback
exit 1
