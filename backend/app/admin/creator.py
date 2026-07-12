from __future__ import annotations

import asyncio
import json

import bcrypt
from sqlalchemy import func, select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.entities import Creator


async def restore_configured_creator() -> int:
    """Restore the configured identity while preserving the sole Creator's id."""
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Creator))
        configured = await session.scalar(
            select(Creator).where(Creator.username == settings.creator_bootstrap_username)
        )
        if configured is not None:
            print(json.dumps({"restored": False, "reason": "configured_creator_exists"}))
            return 0
        if count != 1:
            print(json.dumps({"restored": False, "reason": "expected_exactly_one_creator"}))
            return 1

        creator = await session.scalar(select(Creator))
        if creator is None:
            print(json.dumps({"restored": False, "reason": "creator_not_found"}))
            return 1

        password = settings.creator_bootstrap_password.get_secret_value().encode("utf-8")
        if len(password) > 72:
            print(json.dumps({"restored": False, "reason": "password_exceeds_bcrypt_limit"}))
            return 2

        creator.username = settings.creator_bootstrap_username
        creator.password_hash = bcrypt.hashpw(password, bcrypt.gensalt()).decode("ascii")
        await session.commit()
        print(json.dumps({"restored": True, "id_preserved": True}))
        return 0


def main() -> None:
    raise SystemExit(asyncio.run(restore_configured_creator()))


if __name__ == "__main__":
    main()
