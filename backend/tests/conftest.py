import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-at-least-32-characters")
os.environ.setdefault("CREATOR_BOOTSTRAP_USERNAME", "creator")
os.environ.setdefault("CREATOR_BOOTSTRAP_PASSWORD", "test-password")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/the_creation_os")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
