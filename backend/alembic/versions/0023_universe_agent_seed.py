"""Seed 12 Universes (3 active) and one deterministic Agent per active Universe.

Revision ID: 0023_universe_agent_seed
Revises: 0022_pgvector_extension
Create Date: 2026-07-20 00:00:00.000000

Fix (2026-08-01, Lote: fechar gap de POST /memory + corrigir bug de
migration 0023): the four inserts below originally used unqualified
`ON CONFLICT DO NOTHING`, which matches a conflict on *any* unique
constraint, not just the primary key. `universes.code` and
`capabilities.name` both have their own UNIQUE constraints — if a row
with the same code/name already exists under a *different* id (e.g. a
test fixture inserting `Universe(id=uuid4(), code="knowledge", ...)`
directly, bypassing this migration's canonical static ids), the insert
of this migration's canonical row silently no-ops instead of erring,
leaving that canonical id absent from the table — then the `agents`
insert two loops below, whose `universe_id` FK references that now-
missing canonical id, fails with a confusing FK violation instead of a
clear conflict error at the real point of the problem. Reproduced in
isolation: `alembic upgrade head` from empty, `alembic downgrade 0022`,
`alembic upgrade head` again — the pure migration round trip alone does
NOT reproduce this (proven before writing this fix); it only manifests
once something outside the migration framework has already inserted a
same-code/name row under a non-canonical id. Fixed by qualifying every
`ON CONFLICT` with its real target column(s) (`id` for
universes/capabilities/agents, the composite PK for
agent_capabilities), so the *intended* idempotent case (this exact
canonical row already present) still no-ops silently, while a genuine
code/name collision under a different id now raises a loud, immediate
`UniqueViolation` instead of a delayed, confusing FK error. Edited in
place rather than added as a new migration: the bug is in this
migration's own `upgrade()` logic, so no later migration could fix it
retroactively; and for every environment that already applied 0023
cleanly (the normal case, with no colliding rows), this change produces
the exact same end state — it only changes behavior in the anomalous
conflict case, which was already effectively broken (just failing
later, less clearly). See ARCHITECTURE.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_universe_agent_seed"
down_revision: str | None = "0022_pgvector_extension"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Static ids so upgrade()/downgrade() stay idempotent and symmetric across
# reruns — same convention already used for SYSTEM_WORKER_UUID in
# app/admin/worker.py. See docs/AUDIT_v0.5.md section 10 for the design note.

# (id, code, name, active)
UNIVERSES = [
    ("10000000-0000-0000-0000-000000000001", "knowledge", "Conhecimento", True),
    ("10000000-0000-0000-0000-000000000002", "engineering", "Engenharia", True),
    ("10000000-0000-0000-0000-000000000003", "security", "Segurança", True),
    ("10000000-0000-0000-0000-000000000004", "vision", "Visão", False),
    ("10000000-0000-0000-0000-000000000005", "design", "Design", False),
    ("10000000-0000-0000-0000-000000000006", "business", "Negócios", False),
    ("10000000-0000-0000-0000-000000000007", "marketing", "Marketing", False),
    ("10000000-0000-0000-0000-000000000008", "legal", "Jurídico", False),
    ("10000000-0000-0000-0000-000000000009", "finance", "Finanças", False),
    ("10000000-0000-0000-0000-000000000010", "automation", "Automação", False),
    ("10000000-0000-0000-0000-000000000011", "communication", "Comunicação", False),
    ("10000000-0000-0000-0000-000000000012", "evolution", "Evolução", False),
]

# (id, name, description)
CAPABILITIES = [
    (
        "20000000-0000-0000-0000-000000000001",
        "knowledge_research",
        "Deterministic knowledge synthesis for the Knowledge Universe.",
    ),
    (
        "20000000-0000-0000-0000-000000000002",
        "engineering_design",
        "Deterministic technical proposal drafting for the Engineering Universe.",
    ),
    (
        "20000000-0000-0000-0000-000000000003",
        "security_review",
        "Deterministic risk/permission/secret-exposure review for the Security Universe.",
    ),
]

# (agent_id, code, name, description, universe_code, universe_id, capability_id)
AGENTS = [
    (
        "30000000-0000-0000-0000-000000000001",
        "knowledge-research-agent",
        "Knowledge Research Agent",
        "Organizes information, synthesizes structured findings, and cites internal sources.",
        "knowledge",
        "10000000-0000-0000-0000-000000000001",
        "20000000-0000-0000-0000-000000000001",
    ),
    (
        "30000000-0000-0000-0000-000000000002",
        "engineering-design-agent",
        "Engineering Design Agent",
        "Turns requirements into a technical proposal with components, dependencies, and acceptance criteria. Never executes code.",
        "engineering",
        "10000000-0000-0000-0000-000000000002",
        "20000000-0000-0000-0000-000000000002",
    ),
    (
        "30000000-0000-0000-0000-000000000003",
        "security-review-agent",
        "Security Review Agent",
        "Reviews risk, validates permissions, and checks for exposed secrets against the system's immutable rules.",
        "security",
        "10000000-0000-0000-0000-000000000003",
        "20000000-0000-0000-0000-000000000003",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()

    for universe_id, code, name, active in UNIVERSES:
        conn.execute(
            sa.text(
                "INSERT INTO universes (id, code, name, active) "
                "VALUES (:id, :code, :name, :active) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": universe_id, "code": code, "name": name, "active": active},
        )

    for capability_id, name, description in CAPABILITIES:
        conn.execute(
            sa.text(
                "INSERT INTO capabilities (id, name, description) "
                "VALUES (:id, :name, :description) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": capability_id, "name": name, "description": description},
        )

    for agent_id, code, name, description, universe_code, universe_id, capability_id in AGENTS:
        conn.execute(
            sa.text(
                "INSERT INTO agents "
                "(id, code, name, description, universe, universe_id, enabled, active, status, version) "
                "VALUES (:id, :code, :name, :description, :universe, :universe_id, true, true, 'offline', 1) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": agent_id,
                "code": code,
                "name": name,
                "description": description,
                "universe": universe_code,
                "universe_id": universe_id,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO agent_capabilities (agent_id, capability_id) "
                "VALUES (:agent_id, :capability_id) ON CONFLICT (agent_id, capability_id) DO NOTHING"
            ),
            {"agent_id": agent_id, "capability_id": capability_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for agent_id, *_ in AGENTS:
        conn.execute(sa.text("DELETE FROM agent_capabilities WHERE agent_id = :id"), {"id": agent_id})
    for agent_id, *_ in AGENTS:
        conn.execute(sa.text("DELETE FROM agents WHERE id = :id"), {"id": agent_id})
    for capability_id, *_ in CAPABILITIES:
        conn.execute(sa.text("DELETE FROM capabilities WHERE id = :id"), {"id": capability_id})
    for universe_id, *_ in UNIVERSES:
        conn.execute(sa.text("DELETE FROM universes WHERE id = :id"), {"id": universe_id})
