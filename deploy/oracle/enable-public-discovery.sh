#!/usr/bin/env bash
# Creator-authorized public reading; grants no public-target STF authority.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
cd "$(dirname "$0")/../.."
source deploy/oracle/env-file.sh
[ -f .env ] || { echo 'Existing installation required.' >&2; exit 1; }
umask 077
mkdir -p .connected-backups
backup=".connected-backups/public-discovery-$(date -u +%Y%m%dT%H%M%SZ).env"
cp .env "$backup"
# Limit perception to the reviewed public-news provider. Preserve other configured
# adapters for explicitly authorized missions, outside the discovery worker.
env_set PUBLIC_NEWS_SEARCH_ENABLED true
env_set DEUS_AUTONOMY_DISCOVERY_ENABLED true
env_set DEUS_AUTONOMY_COMPETITION_ENABLED true
env_set PERCEPTION_SENSOR_ALLOWLIST web.search
env_set PERCEPTION_SENSOR_BINDINGS_JSON '{"web.search":{"capability":"web","action":"search"}}'
env_set WEB_PROVIDER_PREFERENCE public-news
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cloud.yml)
if ! "${COMPOSE[@]}" --profile connected-deus up -d --build --force-recreate api worker discovery-worker opportunity-worker; then
  cp "$backup" .env
  "${COMPOSE[@]}" --profile connected-deus up -d --force-recreate api worker discovery-worker opportunity-worker || true
  exit 1
fi
# Observe the real worker config and a bounded research cycle. No private message text
# or provider response is printed. Existing opportunity deduplication remains applied.
"${COMPOSE[@]}" exec -T discovery-worker python - <<'PY'
import asyncio, json
from sqlalchemy import select
from app.config import settings
from app.autonomy.perception import build_perception_fabric
from app.autonomy.discovery import DiscoveryWorker, build_discovery_gateway
from app.db.session import AsyncSessionLocal
from app.diagnostics.worker import creator_scope
from app.models.opportunity import Opportunity

async def main():
    assert settings.public_news_search_enabled and settings.deus_autonomy_discovery_enabled
    creator = await creator_scope()
    assert creator, 'Creator scope missing'
    gateway = build_discovery_gateway()
    perception = build_perception_fabric(gateway, bindings_json=settings.perception_sensor_bindings_json,
                                        allowlist=settings.perception_sensor_allowlist, max_sensors_per_cycle=1)
    report = await DiscoveryWorker(AsyncSessionLocal, perception=perception).run_once(creator)
    print('public_discovery_cycle', json.dumps(report))
    async with AsyncSessionLocal() as session:
        rows = (await session.scalars(select(Opportunity).where(Opportunity.creator_id == creator))).all()
        sectors = sorted({row.sector for row in rows if any(isinstance(ref,str) and ref.startswith('public:https://news.google.com/') for ref in row.evidence_refs_json)})
    print('public_evidence_sectors', json.dumps(sectors))
    assert report['universes_checked'] == 12 and report['sensor_observations'] == 12, 'Public search unavailable in one or more Universes'
    assert len(sectors) == 12, 'Public evidence missing for one or more Universes'

asyncio.run(main())
PY
printf '%s\n' 'Public discovery enabled. External mission authorization and private Cyber Range boundaries preserved.'
