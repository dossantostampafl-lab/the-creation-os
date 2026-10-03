from __future__ import annotations

from datetime import datetime, timedelta


class DiagnosticRules:
    def __init__(self) -> None:
        self.states: dict[str, dict] = {}

    def observe(self, resource: str, healthy: bool | None, now: datetime) -> dict | None:
        row = self.states.setdefault(
            resource,
            {"failures": 0, "successes": 0, "open": False},
        )
        row.update(
            {
                "observed_at": now,
                "valid_until": now + timedelta(seconds=45),
                "status": (
                    "healthy"
                    if healthy is True
                    else "unhealthy"
                    if healthy is False
                    else "unknown"
                ),
            }
        )
        if healthy is None:
            return None

        row["failures"] = 0 if healthy else row["failures"] + 1
        row["successes"] = row["successes"] + 1 if healthy else 0
        if not row["open"] and row["failures"] >= 3:
            row["open"] = True
            return {"resource": resource, "state": "open", "observed_at": now.isoformat()}
        if row["open"] and row["successes"] >= 2:
            row["open"] = False
            return {
                "resource": resource,
                "state": "recovered",
                "observed_at": now.isoformat(),
            }
        return None

    def current(self, resource: str, now: datetime) -> dict:
        row = self.states.get(resource)
        if not row or row["valid_until"] <= now:
            return {"resource": resource, "status": "unknown"}
        return {
            "resource": resource,
            "status": row["status"],
            "observed_at": row["observed_at"].isoformat(),
        }
