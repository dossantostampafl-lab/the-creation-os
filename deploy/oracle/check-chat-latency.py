"""Read bounded sanitized operation timings from the private Tempo service."""
import json
import time

import httpx

with httpx.Client(base_url="http://tempo:3200", timeout=10) as client:
    response = client.get("/api/search", params={"limit": 30, "minDuration": "5s",
        "start": int(time.time()) - 1800, "end": int(time.time())})
    response.raise_for_status()
    for entry in response.json().get("traces", []):
        trace = client.get("/api/traces/" + entry["traceID"])
        trace.raise_for_status()
        spans = []
        for batch in trace.json().get("batches", []):
            for scope in batch.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    name = span.get("name", "")
                    if name.startswith(("deus.", "llm.", "http.")):
                        spans.append({"operation": name,
                            "ms": round((int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1e6)})
        if any(s["operation"] == "deus.turn" for s in spans):
            print(json.dumps({"operations": spans}), flush=True)
