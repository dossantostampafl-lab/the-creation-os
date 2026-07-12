from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


def create_database() -> None:
    _engine = create_async_engine(settings.database_url)
    print('Database creation is managed by alembic migrations.')
