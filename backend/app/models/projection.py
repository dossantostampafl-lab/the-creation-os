from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectionCheckpoint(Base):
    __tablename__ = "projection_checkpoints"

    projection_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
