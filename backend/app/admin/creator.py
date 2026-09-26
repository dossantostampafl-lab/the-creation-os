from __future__ import annotations

import asyncio
import json
import uuid

import bcrypt
from sqlalchemy import func, select

from app.auth.token_store import revoke_refresh_tokens
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.entities import Creator
from app.repositories.domain import DomainRepository


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


async def rotate_creator_password() -> int:
    """Give the Creator the password the environment now holds, and end every open session.

    Rotating is three steps: change CREATOR_BOOTSTRAP_PASSWORD, restart the API so it reads the
    new value, then run this. Ending the sessions is part of it — a rotation that leaves the
    tokens issued under the old password alive has not taken that password back.
    """
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Creator))
        if count != 1:
            print(json.dumps({"rotated": False, "reason": "expected_exactly_one_creator"}))
            return 1

        creator = await session.scalar(select(Creator))
        if creator is None:
            print(json.dumps({"rotated": False, "reason": "creator_not_found"}))
            return 1
        if creator.username != settings.creator_bootstrap_username:
            # Renaming the Creator is restore-creator's job, not this one's.
            print(json.dumps({"rotated": False, "reason": "configured_username_does_not_match"}))
            return 1

        password = settings.creator_bootstrap_password.get_secret_value().encode("utf-8")
        if len(password) > 72:
            print(json.dumps({"rotated": False, "reason": "password_exceeds_bcrypt_limit"}))
            return 2
        if bcrypt.checkpw(password, creator.password_hash.encode("ascii")):
            # Almost always means the environment was never edited, and a rotation that changed
            # nothing must not look like one that did.
            print(json.dumps({"rotated": False, "reason": "password_unchanged"}))
            return 3

        creator.password_hash = bcrypt.hashpw(password, bcrypt.gensalt()).decode("ascii")
        creator_id = creator.id
        await DomainRepository(session).add_event(
            "creator_password_rotated", "creator", creator_id, creator_id, "creator",
            str(uuid.uuid4()), {"origin": "rotate-creator-password"},
        )
        await session.commit()

    revoked = await revoke_refresh_tokens(creator_id)
    print(json.dumps({"rotated": True, "sessions_revoked": revoked}))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(restore_configured_creator()))


def rotate() -> None:
    raise SystemExit(asyncio.run(rotate_creator_password()))


if __name__ == "__main__":
    main()
