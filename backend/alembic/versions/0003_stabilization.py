"""Concurrency, state constraints, and deterministic Chronicle order.

Revision ID: 0003_stabilization
Revises: 0002_living_core_domain
"""
from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa

from alembic import op

revision = "0003_stabilization"
down_revision = "0002_living_core_domain"
branch_labels = None
depends_on = None


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def upgrade() -> None:
    op.add_column("chronicles", sa.Column("position", sa.Integer(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT * FROM chronicles ORDER BY created_at, event_id")).mappings().all()
    previous = None
    for position, row in enumerate(rows, 1):
        material = {"event_id": row["event_id"], "position": position, "event_type": row["event_type"],
                    "aggregate_type": row["aggregate_type"], "aggregate_id": row["aggregate_id"],
                    "actor_id": row["actor_id"], "actor_role": row["actor_role"],
                    "correlation_id": row["correlation_id"], "payload": row["payload_json"],
                    "created_at": row["created_at"].isoformat()}
        digest = hashlib.sha256((_canonical(material) + (previous or "")).encode("utf-8")).hexdigest()
        bind.execute(sa.text("UPDATE chronicles SET position=:position, previous_hash=:previous, payload_hash=:digest WHERE event_id=:event_id"),
                     {"position": position, "previous": previous, "digest": digest, "event_id": row["event_id"]})
        previous = digest
    op.alter_column("chronicles", "position", nullable=False)
    op.create_unique_constraint("uq_chronicles_position", "chronicles", ["position"])
    op.create_check_constraint("ck_conversation_status", "conversations", "status IN ('active','closed','archived')")
    op.create_check_constraint("ck_inception_status", "inceptions", "status IN ('proposed','awaiting_creator_decision','approved','rejected','cancelled')")
    op.create_check_constraint("ck_mission_status", "missions", "status IN ('drafted','planned','validated','authorized','distributed','executing','manifested','failed','cancelled')")


def downgrade() -> None:
    op.drop_constraint("ck_mission_status", "missions", type_="check")
    op.drop_constraint("ck_inception_status", "inceptions", type_="check")
    op.drop_constraint("ck_conversation_status", "conversations", type_="check")
    op.drop_constraint("uq_chronicles_position", "chronicles", type_="unique")
    op.drop_column("chronicles", "position")
