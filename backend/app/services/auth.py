from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.models.entities import Creator
from app.repositories.auth import CreatorRepository
from app.schemas.auth import TokenPayload


class AuthService:
    def __init__(self, repository: CreatorRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    @classmethod
    def create(cls, session: AsyncSession) -> 'AuthService':
        return cls(CreatorRepository(session), session)

    async def bootstrap(self, username: str, password: str) -> Creator:
        existing = await self.repository.get_one()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Creator already exists")
        # The check above is only a fast path — it cannot by itself prevent a
        # second concurrent bootstrap from also observing "no Creator yet"
        # before either transaction commits. The real guard is the
        # `uq_creator_singleton` unique constraint (migration
        # 0024_creator_singleton): at most one row can ever have
        # `singleton = true`, so a second concurrent insert fails at the
        # database level and is translated to the same 409 here.
        try:
            creator = await self.repository.create(username=username, password=password)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Creator already exists") from exc
        return creator

    async def login(self, username: str, password: str) -> Creator:
        creator = await self.repository.get_by_username(username)
        if creator is None or not await self.repository.verify_password(creator, password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return creator

    def create_token(self, subject: str, token_type: str, expires_delta: timedelta) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": subject,
            "type": token_type,
            "exp": now + expires_delta,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")

    def create_access_token(self, subject: str) -> str:
        return self.create_token(subject, "access", settings.access_token_expires)

    def create_refresh_token(self, subject: str) -> str:
        return self.create_token(subject, "refresh", settings.refresh_token_expires)

    def decode_token(self, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=["HS256"])
            return TokenPayload(**payload)
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


async def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService.create(session)
