from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_creator, get_current_token
from app.auth.rate_limit import LoginRateLimiter, get_login_rate_limiter
from app.config import settings
from app.core.domain import Actor
from app.repositories.god import GodConversationRepository
from app.schemas.auth import BootstrapRequest, CreatorResponse, LoginRequest, TokenPayload, TokenResponse
from app.services.auth import get_auth_service
from app.services.greeting import maybe_send_login_greeting

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap", response_model=CreatorResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap(request: BootstrapRequest, auth_service = Depends(get_auth_service)) -> CreatorResponse:
    creator = await auth_service.bootstrap(request.username, request.password.get_secret_value())
    return CreatorResponse(
        id=creator.id,
        username=creator.username,
        is_active=creator.is_active,
        created_at=creator.created_at,
        updated_at=creator.updated_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    auth_service = Depends(get_auth_service),
    rate_limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> TokenResponse:
    client_ip = http_request.client.host if http_request.client else "unknown"
    await rate_limiter.check(client_ip, request.username)
    try:
        creator = await auth_service.login(request.username, request.password.get_secret_value())
    except HTTPException:
        # Only failed attempts count toward the limit — see LoginRateLimiter's
        # docstring for why a successful login doesn't, and clears prior
        # failures for this ip+username instead.
        await rate_limiter.record_failure(client_ip, request.username)
        raise
    await rate_limiter.reset(client_ip, request.username)
    access_token = auth_service.create_access_token(creator.id)
    refresh_token = auth_service.create_refresh_token(creator.id)
    # Lote: DEUS inicia conversa automaticamente após login. Only a real
    # login triggers this — /auth/refresh (below) is unchanged and never
    # calls it, matching the lote's explicit "não ao refresh" scope.
    conversation_id = await maybe_send_login_greeting(
        GodConversationRepository(auth_service.session),
        Actor(id=creator.id, role="creator"),
        str(uuid.uuid4()),
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes,
        conversation_id=conversation_id,
    )


@router.get("/me", response_model=CreatorResponse)
async def me(token_payload = Depends(get_current_creator), auth_service = Depends(get_auth_service)) -> CreatorResponse:
    # token_payload.sub is the Creator's id, not username — create_access_token()
    # is always called with creator.id (see login()/refresh() below). Looking it
    # up via get_by_username() (the prior code here) meant this route 404'd for
    # every real caller, since a UUID essentially never matches a real username.
    # Found by the audit's own test for this endpoint — there was none before.
    creator = await auth_service.repository.get_by_id(token_payload.sub)
    if creator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return CreatorResponse(
        id=creator.id,
        username=creator.username,
        is_active=creator.is_active,
        created_at=creator.created_at,
        updated_at=creator.updated_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(token_payload: TokenPayload = Depends(get_current_token), auth_service = Depends(get_auth_service)) -> TokenResponse:
    if token_payload.type != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    access_token = auth_service.create_access_token(token_payload.sub)
    refresh_token = auth_service.create_refresh_token(token_payload.sub)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=settings.access_token_expire_minutes)
