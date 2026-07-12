from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Creator


class CreatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_one(self) -> Creator | None:
        result = await self.session.execute(select(Creator).limit(1))
        return result.scalars().first()

    async def get_by_username(self, username: str) -> Creator | None:
        result = await self.session.execute(select(Creator).where(Creator.username == username))
        return result.scalars().first()

    async def get_by_id(self, creator_id: str) -> Creator | None:
        return await self.session.get(Creator, creator_id)

    async def create(self, username: str, password: str) -> Creator:
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            raise ValueError("Password exceeds bcrypt's 72-byte limit")
        creator = Creator(username=username, password_hash=bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii"))
        self.session.add(creator)
        await self.session.flush()
        return creator

    async def verify_password(self, creator: Creator, password: str) -> bool:
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            return False
        return bcrypt.checkpw(password_bytes, creator.password_hash.encode("ascii"))
