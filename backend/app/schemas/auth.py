from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class BootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: SecretStr = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: SecretStr = Field(..., min_length=8, max_length=128)


class TokenPayload(BaseModel):
    sub: str
    type: Literal["access", "refresh"]
    jti: str
    exp: int


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CreatorResponse(BaseModel):
    id: str
    username: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
