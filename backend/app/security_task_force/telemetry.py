from __future__ import annotations

import json
import logging
from typing import Any

from .evidence import redact

log = logging.getLogger("stf")


def emit(event: str, *, mission_id: str, action_id: str | None = None, evidence_id: str | None = None,
         environment_id: str | None = None, **fields: Any) -> dict[str, Any]:
    """One structured line per transition, decision, grant, dispatch, verification or kill."""
    record = {"event": event, "mission_id": mission_id, "action_id": action_id, "evidence_id": evidence_id,
              "environment_id": environment_id, **redact(fields)}
    log.info(json.dumps(record, sort_keys=True, default=str))
    return record
