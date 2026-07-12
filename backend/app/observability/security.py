from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger


def log_blocked_action(*, actor_id: str, action: str, resource: str, correlation_id: str, reason: str) -> None:
    """Security audit stream, deliberately separate from the domain Chronicle."""
    logger.bind(
        security_event="authenticated_action_blocked",
        actor_id=actor_id,
        action=action,
        resource=resource,
        correlation_id=correlation_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        reason=reason,
    ).warning("authenticated action blocked")
