"""Read bounded sanitized operation timings through private Grafana."""
import argparse
import base64
import json
import sys
import time
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
args = parser.parse_args()
password = sys.stdin.readline().rstrip('\n')
header = 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def get(path):
    request = urllib.request.Request('http://127.0.0.1:' + str(args.port) +
        '/api/datasources/proxy/uid/tempo' + path, headers={'Authorization': header})
    with opener.open(request, timeout=10) as response:
        return json.load(response)

if __name__ == "__main__":
    result = get("/api/search?" + urllib.parse.urlencode({"limit": 30, "minDuration": "5s",
        "start": int(time.time()) - 1800, "end": int(time.time())}))
    print(json.dumps({"traces_found": len(result.get("traces", []))}), flush=True)
    for entry in result.get("traces", []):
        trace = get("/api/traces/" + entry["traceID"])
        spans = []
        for batch in trace.get("batches", []):
            for scope in batch.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    name = span.get("name", "")
                    if name.startswith(("deus.", "llm.", "http.")):
                        spans.append({"operation": name,
                            "ms": round((int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1e6)})
        if any(s["operation"] == "deus.turn" for s in spans):
            print(json.dumps({"operations": spans}), flush=True)
