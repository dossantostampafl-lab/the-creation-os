"""Read-only checks through the authenticated loopback Grafana proxy."""
from __future__ import annotations
import argparse
import base64
import json
import sys
import time
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--trace', required=True)
args = parser.parse_args()
password = sys.stdin.readline().rstrip('\n')
header = 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    request = urllib.request.Request('http://127.0.0.1:' + str(args.port) + path,
                                     headers={'Authorization': header})
    with opener.open(request, timeout=5) as response:
        return json.load(response)

checks = {
    'tempo': lambda: get('/api/datasources/proxy/uid/tempo/api/traces/' + args.trace),
    'prometheus': lambda: get('/api/datasources/proxy/uid/prometheus/api/v1/query?' +
        urllib.parse.urlencode({'query': 'creation_operation_count_total{operation="http.server"}'}))['data']['result'],
    'loki': lambda: get('/api/datasources/proxy/uid/loki/loki/api/v1/query_range?' +
        urllib.parse.urlencode({'query': '{job="creation-operations",operation="http.server"} |= "' + args.trace + '"', 'limit': '1'}))['data']['result'],
    'dashboards': lambda: len(get('/api/search?tag=creation-os')) == 8,
    'infrastructure': lambda: get('/api/datasources/proxy/uid/prometheus/api/v1/query?' +
        urllib.parse.urlencode({'query': 'node_memory_MemAvailable_bytes'}))['data']['result'],
    'snapshots': lambda: get('/api/datasources/proxy/uid/prometheus/api/v1/query?' +
        urllib.parse.urlencode({'query': 'creation_snapshot_age_seconds'}))['data']['result'],
}
for attempt in range(30):
    pending = []
    for name, check in checks.items():
        try:
            if not check(): pending.append(name)
        except Exception:
            pending.append(name)
    if not pending:
        print('Observability verified: traces, metrics, logs, 8 dashboards, infrastructure and state snapshots.')
        break
    if attempt == 29:
        raise SystemExit('Observability incomplete: ' + ', '.join(pending))
    time.sleep(3)
