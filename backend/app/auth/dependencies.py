from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.observability.security import log_blocked_action
from app.schemas.auth import TokenPayload
from app.services.auth import get_auth_service


async def get_current_token(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> TokenPayload:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    token = authorization.removeprefix("Bearer ")
    auth_service = await get_auth_service(session)
    return auth_service.decode_token(token)


async def get_current_creator(token_payload: TokenPayload = Depends(get_current_token)) -> TokenPayload:
    if token_payload.type != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return token_payload


async def get_sovereign_creator(
    token_payload: TokenPayload = Depends(get_current_creator),
    session: AsyncSession = Depends(get_session),
    x_correlation_id: str | None = Header(None),
) -> TokenPayload:
    auth_service = await get_auth_service(session)
    creator = await auth_service.repository.get_one()
    # sovereign creator id can be set via environment/config
    configured_id = None
    sovereign_id = configured_id or (creator.id if creator is not None else None)
    if creator is None or not creator.is_active or token_payload.sub != sovereign_id or creator.id != sovereign_id:
        log_blocked_action(actor_id=token_payload.sub, action="assume_sovereign_creator_authority",
                           resource="living_core", correlation_id=x_correlation_id or "missing",
                           reason="subject is not the configured sovereign Creator")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sovereign Creator authority required")
    return token_payload
