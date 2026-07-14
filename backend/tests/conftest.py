import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-at-least-32-characters")
os.environ.setdefault("CREATOR_BOOTSTRAP_USERNAME", "creator")
os.environ.setdefault("CREATOR_BOOTSTRAP_PASSWORD", "test-password")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
