# THE CREATION OS Architecture

## Immutable flow

```text
Creator -> Creator Interface -> DEUS / SOPHIA / ROCKMAM -> Inception
        -> Central Core -> Tree Core -> Universes -> Agents
        -> Tree Core -> Central Core -> Malkuth
```

## Tree Core Foundation v0.4.1

Tree Core currently owns only agent discovery and capability-based selection.
The Agent Registry persists agent identity, universe label, lifecycle state,
priority, heartbeat, and normalized capabilities. The Capability Engine checks
an authorized Mission and returns eligible agents ordered by priority.

Eligibility requires:

- enabled agent;
- `idle` status;
- every requested capability;
- heartbeat no older than five minutes.

Tree Core does not create, approve, authorize, dispatch, execute, aggregate, or
manifest Missions. Dispatch, Execution, Aggregation, complete Universes, Pulse,
and Malkuth remain outside v0.4.1.

## Mission Planner v0.4.2

An authorized Mission is a strategic objective. The deterministic planner creates
a cycle-free Task DAG. Tasks are operational planning units. Dispatch and execution
do not exist in this version.

## Dispatch Queue v0.4.3

The queue persists future Task routing decisions after Capability Engine matching.
Leasing uses PostgreSQL row locks and opaque high-entropy tokens stored only as
SHA-256 hashes. The queue has no worker and performs no execution.

## Agent Dispatcher Protocol v0.4.4

**STATUS: FROZEN.** The Agent Dispatcher remains a protocol-only boundary. No
runtime, polling, worker process, Agent invocation, Task execution, Mission
execution, or manifestation belongs to this version.

The Agent Dispatcher is a protocol boundary after Dispatch Queue. Persistent
workers announce normalized capabilities and authenticate with opaque credentials.
A claim returns a lease-bound Execution Envelope; it never invokes an Agent.
Heartbeat never renews a lease, and retry, timeout, or shutdown grants no authority.
There is no runtime, permanent worker, scheduler, automatic processing, or
manifestation in this version.

## Agents v0.4.5

Controlled execution belongs to the existing Agents block. Dispatch Queue and
Agent Dispatcher remain internal mechanisms between Capability Engine and Agents.
Only registered deterministic handlers with no side effects can run. Every result
returns to Tree Core; Malkuth remains responsible for manifestation.

## Central Core Decision

Central Core reads Tree Core mission consolidations and records immutable
decisions. It does not change Mission, Task, DispatchItem, AgentExecution, or
MissionConsolidation records. A recorded decision becomes available for later
policy reasoning and Malkuth manifestation.

## DEUS, SOPHIA, ROCKMAM

DEUS conversation, SOPHIA understanding, and ROCKMAM assessment are separate
bounded steps. They may interpret, understand, and assess, but they do not create
Mission automatically and do not bypass Creator authorization.

## Memory, Automation, Opportunity, Perception

Memory provides Creator context. Automation connectors remain capability-governed.
Opportunity Discovery and Continuous Perception may collect, rank, notify, and
support Creator review, but they do not authorize Mission and do not manifest.

## Release Candidate Boundary

The release-candidate health boundary is Alembic `0024_creator_singleton`.
Readiness requires PostgreSQL, Redis, and the expected migration revision. This
document records architecture only; it does not authorize new layers, engines,
workers, endpoints, or responsibility shifts.

## Creator Interface — Living Universe Motion

The initial Creator Interface screen (`frontend/src/components/LivingDashboard.tsx`)
renders the universe as a single `<canvas>` driven by one `requestAnimationFrame`
loop (`LivingUniverseScene`), not a static image. This is the already-accepted
direction on this branch (see commit history and `docs/AUDIT_v0.5.md`); the
sidebar-vs-universe boundary the spec actually protects (no persistent
sidebar/menu/dashboard-grid) remains untouched and is guarded by
`frontend/src/components/LivingDashboard.frozenSpec.test.ts`.

Taste calls made while adding continuous motion (all chosen for the most
subtle, reversible value, per the batch's own instruction not to stop and ask):

- **Canvas motion** (particle drift, hotspot orbit/breathing, constellation
  twinkle, neural-path signal travel) was already implemented before this
  batch; this batch only made `prefers-reduced-motion` reactive to a live OS
  toggle instead of a mount-time-only check (a `MediaQueryList` `change`
  listener updates a closured `reducedMotion` flag read by the existing draw
  loop; cleaned up alongside the existing `ResizeObserver`/`pointermove`
  cleanup).
- **DOM finishing touches** added on top of already-existing elements only
  (no new structural elements): a 7s opacity/scale breathing loop on the DEUS
  label, a 2.6s pulse on the chronicle-ticker status dot, a 5s opacity
  breathing loop on the system-state-binding pill (only while
  `loadState === "ready"`, i.e. only when genuinely healthy), a 600ms
  `stroke-dasharray` transition on the pulse-score ring so score changes
  glide instead of snapping, a 120ms opacity fade on the hotspot tooltip, and
  a 420ms fade/scale-in on constellation cards (covers a universe card
  appearing when a universe goes active).
- All new animations use `transform`/`opacity` (or, for the pulse-score ring,
  an infrequent data-driven SVG attribute transition, not a per-frame one) —
  no `width`/`height`/`top`/`left` animation was added.
- All new CSS animations are covered by the existing global
  `@media (prefers-reduced-motion: reduce)` rule
  (`frontend/src/styles/living-dashboard.css`), which already zeroes
  `animation-duration` for every element; no per-animation opt-out was
  needed.
- No new animation dependency was added. `@types/node` was added as a
  dev-only dependency so the new frozen-spec regression test can read source
  files with `node:fs`; it has no runtime/bundle effect (confirmed by
  `npm run build` output).
