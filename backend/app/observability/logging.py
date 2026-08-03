from __future__ import annotations

import contextvars
import json
import sys
from datetime import timezone
from typing import Any

from loguru import logger

from app.repositories.domain import sanitize

SERVICE_NAME = "the-creation-os-api"

# Request-scoped context, set once per request by app.main's observe_request
# middleware (the same correlation_id it also echoes in the X-Correlation-ID
# response header — Lote: logging JSON estruturado, correção do "não ecoa o
# UUID gerado internamente" achado na auditoria anterior). Any log call
# anywhere during that request — including deep in a service/repository
# with no direct access to the FastAPI request object — picks this up
# automatically unless it explicitly binds its own correlation_id/actor_id.
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)
_actor_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("actor_id", default=None)


def set_log_context(*, correlation_id: str | None = None, actor_id: str | None = None) -> None:
    _correlation_id_var.set(correlation_id)
    _actor_id_var.set(actor_id)


def reset_log_context() -> None:
    _correlation_id_var.set(None)
    _actor_id_var.set(None)


def record_to_json(record: dict[str, Any]) -> str:
    """The exact flat shape the original v0.3 document requires: timestamp,
    level, service, event, correlation_id, actor_id, aggregate_type,
    aggregate_id, message — plus whatever else a caller bound, minus
    anything SENSITIVE_KEYS matches. A pure function of a loguru record
    dict specifically so it's directly unit-testable without going through
    loguru's own sink plumbing."""
    extra = record["extra"]
    payload: dict[str, Any] = {
        "timestamp": record["time"].astimezone(timezone.utc).isoformat(),
        "level": record["level"].name,
        "service": SERVICE_NAME,
        "event": extra.get("event") or record["name"],
        "correlation_id": extra.get("correlation_id") or _correlation_id_var.get(),
        "actor_id": extra.get("actor_id") or _actor_id_var.get(),
        "aggregate_type": extra.get("aggregate_type"),
        "aggregate_id": extra.get("aggregate_id"),
        "message": record["message"],
    }
    for key, value in extra.items():
        if key not in payload:
            payload[key] = value
    # SENSITIVE_KEYS/sanitize() — the same function Chronicles (app/repositories/
    # domain.py) already uses on payload_json — reused here, not duplicated,
    # as a backstop: redacts automatically if a caller ever binds a sensitive
    # key, rather than relying on every call site remembering not to.
    return json.dumps(sanitize(payload), default=str, ensure_ascii=False)


def _stdout_sink(message) -> None:
    sys.stdout.write(record_to_json(message.record) + "\n")


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(_stdout_sink, level=level)
