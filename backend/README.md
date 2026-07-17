# THE CREATION OS backend

## Release Candidate Baseline

The backend release-candidate baseline expects Alembic head
`0021_mission_authorization`. The readiness endpoint verifies PostgreSQL, Redis,
and this exact migration revision before returning ready.

Operational endpoints:

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`

The backend does not require external LLM, embedding, GitHub, or ElevenLabs
credentials for the default fake-provider development path.

## Tree Core v0.4.1

The Tree Core foundation contains two bounded components:

- Agent Registry: persistent agents, heartbeats, enable/disable state, and
  normalized capability assignments.
- Capability Engine: read-only selection of eligible agents for an authorized
  Mission, ordered by descending priority.

All Tree Core endpoints require sovereign Creator authentication. Matching does
not dispatch work and does not mutate the Mission.

Not included in v0.4.1: Dispatch, Execution, Aggregation, complete Universes,
Pulse, or Malkuth manifestation.

## Agent Dispatcher Protocol v0.4.4

**STATUS: FROZEN.** Functional changes are closed for this version. The final
evidence and known residual risks are recorded in
`../docs/V044_FINAL_AUDIT.md`.

The protocol adds a persistent Worker Registry, normalized capabilities,
heartbeat, opaque-credential authentication, claim with an Execution Envelope,
and acknowledge, release, fail, and shutdown operations. Credentials are stored
only as hashes. It contains no runtime, polling loop, scheduler, agent execution,
or automatic processing.

## Agents v0.4.5

Controlled Task execution validates the authorized Mission, ready Task, eligible
Agent, capability, authenticated Worker, lease ownership, deadline, and registered
handler before running. Handlers are deterministic internal callables with no
filesystem, network, shell, subprocess, dynamic import, or manifestation access.
Structured results return only to Tree Core.

## Central Core and Later Release-Candidate Scope

Central Core records immutable decisions over Tree Core consolidations. Policy,
Malkuth, GOD, SOPHIA, ROCKMAM, memory, automation, opportunity discovery,
continuous perception, and mission authorization exist as separate bounded
modules. This README is not an authorization to merge those responsibilities.

For reproducible validation, use the root `README.md`, `backend/TESTING.md`, and
`../docs/RELEASE_CHECKLIST.md`.
