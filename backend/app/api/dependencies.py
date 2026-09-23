from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor
from app.schemas.auth import TokenPayload


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    """Canonical correlation id for a mutation: the caller's UUID, or a new one."""
    if x_correlation_id is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(x_correlation_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Correlation-ID must be a UUID") from exc


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")
