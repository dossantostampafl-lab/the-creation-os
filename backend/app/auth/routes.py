from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_creator, get_current_token
from app.config import settings
from app.schemas.auth import BootstrapRequest, CreatorResponse, LoginRequest, TokenPayload, TokenResponse
from app.services.auth import get_auth_service

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
async def login(request: LoginRequest, auth_service = Depends(get_auth_service)) -> TokenResponse:
    creator = await auth_service.login(request.username, request.password.get_secret_value())
    access_token = auth_service.create_access_token(creator.id)
    refresh_token = await auth_service.issue_refresh_token(creator.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=settings.access_token_expire_minutes)


@router.get("/me", response_model=CreatorResponse)
async def me(token_payload = Depends(get_current_creator), auth_service = Depends(get_auth_service)) -> CreatorResponse:
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
    refresh_token = await auth_service.rotate_refresh_token(token_payload)
    access_token = auth_service.create_access_token(token_payload.sub)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=settings.access_token_expire_minutes)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(token_payload: TokenPayload = Depends(get_current_creator), auth_service = Depends(get_auth_service)) -> None:
    await auth_service.revoke_refresh_tokens(token_payload.sub)
