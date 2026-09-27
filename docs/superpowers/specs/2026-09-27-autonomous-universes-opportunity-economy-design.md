# Autonomous Universes, Opportunity Fabric and Economic Core — Design Specification

**Status:** DESIGN_FROZEN_PENDING_CREATOR_REVIEW  
**Date:** 2026-09-27  
**Repository:** `dossantostampafl-lab/the-creation-os`  
**Implementation target:** one consolidated PR after spec and plan review  

## 1. Purpose

This specification consolidates the decisions approved across Council Rounds 1–10 for THE CREATION OS. It defines how the canonical 12 Universes perceive, discover, compare, select, execute and learn from economically relevant opportunities while reusing the current Creation runtime instead of introducing a second architecture.

The design principle is strict: **extend the existing Creation kernel first; create a new component only when no current component can correctly own the responsibility.**

This document is normative for the subsequent implementation plan. No production code is to be changed from this specification alone; implementation begins only after Creator review and approval of the spec and implementation plan.

## 2. Design goals

1. Restore the canonical 12 Universes as first-class autonomous fields of intelligence.
2. Let every Universe perceive and discover opportunities across sectors rather than behave as a rigid department.
3. Preserve independent cognition and memory while sharing verified evidence where useful.
4. Allow autonomous execution inside a bounded, persistent mission envelope without requiring approval for every micro-action.
5. Reuse `Mission`, `Task`, `AgentRuntime`, `CapabilityRuntime`, `CapabilityGateway`, `UniverseMemory` and `Chronicle` as the operational core.
6. Add the minimum persistent state needed for opportunity competition and economic accounting.
7. Treat MCPs, plugins, crawlers, browsers and external tools as replaceable capability providers, not architectural layers.
8. Require reconciled real outcomes before economic results become settled capital.
9. Preserve the frozen governance rule that lower layers may restrict authority but never expand it.
10. Deliver implementation in one PR, internally split into independently testable TDD gates.

## 3. Non-goals

The implementation must not create:

- a separate Perception Broker service;
- a separate Action Orchestrator;
- an Economic Runtime;
- a proprietary MCP platform;
- a proprietary plugin platform;
- twelve independent crawling stacks;
- twelve separate execution runtimes;
- a second Capability Gateway;
- a new orchestration layer solely for opportunity execution;
- a rule that binds a Universe to one economic sector.

## 4. Canonical system flow

```text
CREATOR
   ↓
DEUS
   ↓
SOPHIA
   ↓
ROCKMAM
   ↓
────────────────────────────────
MISSION ORIGIN
────────────────────────────────
   ↓                      ↓
Creator Inception      Opportunity
   └─────────────┬───────────┘
                 ↓
               Mission
                 ↓
       autonomy / authorization envelope
                 ↓
            12 Universes
                 ↓
        Agents + UniverseMemory
                 ↓
            AgentRuntime
                 ↓
         CapabilityRuntime
                 ↓
         CapabilityGateway
                 ↓
 Web / Workspace / PROTO / MCP / crawler /
 browser / API / plugin-backed capabilities
                 ↓
              Result
                 ↓
     Chronicle + Economic Ledger
                 ↓
             Learning
                 ↺
```

A Mission remains the execution vehicle. Opportunity is an alternate valid source of Mission, not a replacement runtime.

## 5. Canonical 12 Universes

The canonical identities are:

1. `knowledge` — Conhecimento
2. `engineering` — Engenharia
3. `security` — Segurança
4. `vision` — Visão
5. `design` — Design
6. `business` — Negócios
7. `marketing` — Marketing
8. `legal` — Jurídico
9. `finance` — Finanças
10. `automation` — Automação
11. `communication` — Comunicação
12. `evolution` — Evolução

Historical static UUIDs should be preserved if reconciliation with the current schema proves safe and deterministic. Restoration must be idempotent.

A Universe is **not a department**. It is an autonomous field of perception, creation, strategy and learning with an initial cognitive bias. Sector/domain is an attribute of an opportunity, not a boundary of a Universe.

The same Universe may discover opportunities in multiple sectors. Multiple Universes may independently investigate, compete or collaborate around the same opportunity.

## 6. Perception Cell as composition, not new infrastructure

Each Universe has its own Perception Cell conceptually, but it is implemented as a composition of existing runtime elements rather than as a new service or table.

```text
Perception Cell
=
Universe
+ Agent(s)
+ UniverseMemory
+ capabilities
+ preferred sensors
+ detector weights
+ exploration strategy
+ learned patterns
```

The initial bias of each Universe influences what it notices first, but does not constrain what it is allowed to perceive.

### 6.1 Initial sensor and detector priors

- **Knowledge:** search, documents, APIs, RSS; information gaps, recurring pain, demand gaps.
- **Engineering:** code, GitHub, technical docs, issues, releases; capability gaps, efficiency gaps, technology shifts.
- **Security:** advisories, code, technical feeds; risk/capability gaps, technology shifts, regulatory changes.
- **Vision:** news, trends, social and public market signals; trend acceleration, behavior change, temporal windows.
- **Design:** browsers, products, reviews, interfaces; pain recurrence, conversion friction, attention gaps.
- **Business:** marketplaces, suppliers, prices, reviews; demand gaps, supply scarcity, price gaps, arbitrage.
- **Marketing:** search, social, content and reviews; attention gaps, demand gaps, trend acceleration, conversion friction.
- **Legal:** official sources, legislation, jurisprudence and documents; regulatory changes, information gaps, recurring pain.
- **Finance:** PROTO, public market data, prices and macro data; price gaps, arbitrage, temporal windows and supply/demand imbalance.
- **Automation:** APIs, workflows, integrations, SaaS ecosystems; efficiency gaps, capability gaps and capacity mismatches.
- **Communication:** media, communities, social and search; attention gaps, behavior change and demand gaps.
- **Evolution:** Chronicle, metrics, tests and outcomes from the other Universes; regressions, drift, performance gaps and novel patterns.

These are priors, not permissions.

## 7. Sensors, MCPs, plugins and external providers

The Creation owns stable capability names. External tools supply those capabilities behind replaceable adapters.

Examples of stable logical capabilities:

- `web.fetch`
- `web.search`
- `web.crawl`
- `web.extract`
- `browser.observe`
- `browser.interact`
- `research.semantic`
- `specialized.web`
- `market.read`
- `workspace.*`

Possible providers include local HTTP, Crawlee, Crawl4AI, Playwright MCP, Firecrawl, Exa, Tavily, Brave, Apify, Browser Use and future certified providers.

The Universe requests a capability; it does not hardcode a vendor.

Provider selection may consider:

- cost;
- latency;
- freshness;
- reliability;
- evidence quality;
- rate limits;
- prior success;
- authentication requirements;
- operational health.

MCP Registry, if integrated, is a discovery catalog only. Discovery never grants execution authority. A newly discovered provider must pass origin, license, security, capability and shadow/replay evaluation before becoming enabled.

Public normally accessible information is allowed for read-only perception. The system must not bypass login, paywall, CAPTCHA, access controls or permissions. Read access grants perception only, not downstream execution authority.

## 8. Shared evidence, private cognition

Verified evidence may be reused across Universes to avoid paying twelve times for the same acquisition.

The sharing model is:

- **Evidence:** shareable
- **Interpretation:** Universe-specific
- **Hypothesis:** Universe-specific
- **Strategy:** Universe-specific
- **Memory:** Universe-specific

A Universe does not inherit another Universe's thesis merely because it can see the evidence.

## 9. Detection and hypothesis formation

Atomic detector families available to all Universes include:

- Demand Gap
- Price Gap
- Pain Recurrence
- Trend Acceleration
- Supply Scarcity
- Capability Gap
- Efficiency Gap
- Attention Gap
- Information Gap
- Temporal Window
- Underutilized Asset
- Reward
- Arbitrage
- Capacity Mismatch
- Conversion Friction
- Regulatory Change
- Technology Shift
- Behavior Change

No detector alone declares an opportunity. Detectors produce evidence-backed claims. Composite patterns produce hypotheses.

A viable hypothesis must define at minimum:

- real problem, gap or demand;
- measurable value;
- target payer or value recipient;
- capture mechanism;
- delivery/execution path;
- estimated cost;
- expected value;
- bounded downside;
- time window;
- supporting evidence;
- confidence;
- falsification conditions;
- observable settlement path.

## 10. Minimal persistent domain model

Only four new persistent objects are required in the initial implementation.

### 10.1 `Opportunity`

Represents the underlying economic opportunity independent of a particular solution.

Minimum fields:

- `id`
- `creator_id`
- `fingerprint`
- `sector`
- `problem_or_gap`
- `capture_mechanism`
- `evidence_refs_json`
- `first_discovered_by_universe_id`
- `time_window_json`
- `status`
- `created_at`
- `updated_at`

`fingerprint` is used for deterministic clustering/deduplication in the first version. No separate `OpportunityCluster` table is required initially.

### 10.2 `OpportunityThesis`

Represents one Universe's proposed way to capture value from an Opportunity.

Minimum fields:

- `id`
- `opportunity_id`
- `universe_id`
- `proposed_value`
- `target_payer`
- `capture_path`
- `estimated_cost_json`
- `expected_value_json`
- `max_downside_json`
- `confidence`
- `falsification_conditions_json`
- `evidence_refs_json`
- `status`
- `created_at`
- `updated_at`

Collaborative attribution may initially live in structured JSON and Chronicle events instead of a new persistence model.

### 10.3 `OpportunityLease`

Controls concurrency and guarantees at most one material execution path for a given opportunity.

Minimum fields:

- `id`
- `opportunity_id`
- `thesis_id`
- `universe_id`
- `lease_type`
- `status`
- `acquired_at`
- `expires_at`
- `released_at`

Concurrent research leases may exist. Executive lease exclusivity must be enforced by the database, not only by application code.

### 10.4 `EconomicLedgerEntry`

Append-oriented economic truth for each Universe.

Minimum fields:

- `id`
- `creator_id`
- `universe_id`
- `mission_id`
- `opportunity_id`
- `entry_type`
- `amount`
- `currency`
- `status`
- `external_reference`
- `metadata_json`
- `created_at`
- `settled_at`

Account balance, NAV, drawdown and available capital should initially be derived projections rather than a separate mutable account table.

## 11. Opportunity lifecycle

Initial lifecycle:

```text
DETECTED
→ QUALIFYING
→ COMPETING
→ CHALLENGED
→ SELECTED
→ AUTH_PENDING
→ AUTHORIZED
→ RESERVED
→ EXECUTING
→ RECONCILING
→ SETTLED
→ LEARNED
```

Side exits:

- `REJECTED`
- `EXPIRED`
- `CANCELLED`
- `RECONCILIATION_REQUIRED`

The implementation may collapse purely presentational intermediate states if doing so preserves the invariants and reduces unnecessary persistence.

## 12. Competition and collaboration

Multiple Universes may submit theses for one Opportunity. Theses are compared across dimensions rather than collapsed into one opaque score.

Relevant comparison dimensions include:

- expected net value;
- evidence strength;
- estimated probability of success;
- capital efficiency;
- time to value;
- downside;
- reversibility;
- scalability;
- novelty;
- operational complexity;
- reconciliation quality.

Weights depend on opportunity context.

Universes may combine contributions into a composite thesis. Attribution must preserve discoverer, lead Universe, confirmations and meaningful contributors.

Selection does not grant authority. The selected thesis must still become a Mission governed by the normal mission envelope.

## 13. Mission origin generalization

Current Mission creation is tied to `Inception`. Autonomous economic opportunities require a second legitimate source.

The Mission model must be generalized so that exactly one origin exists:

```text
CREATOR_INCEPTION:
  inception_id != null
  opportunity_id = null

OPPORTUNITY:
  inception_id = null
  opportunity_id != null
```

The invariant must be enforced at the database level and validated in application code.

There must be no fabricated Creator message and no artificial Inception for autonomous opportunities.

After origin resolution, both paths use the same existing Mission, MissionPlan, MissionStep, Task, AgentRuntime and capability execution flow.

## 14. Autonomy envelope

The existing Mission authorization model is the basis for autonomy. It should be extended rather than replaced.

The envelope includes at least:

- allowed capabilities;
- denied capabilities;
- scope;
- external effect policy;
- risk ceiling;
- budget;
- expiration;
- authorization version;
- environment/domain bounds where applicable.

Core rule:

```text
inside the valid envelope → continue automatically
outside the valid envelope → stop/escalate at that boundary only
```

The Creation must not request manual approval for every low-impact action that is already covered by the active envelope.

Capital availability does not grant authority.

## 15. Economic core

The economic model is cross-sector and not centered on PROTO.

PROTO remains one finance-domain capability/provider.

### 15.1 CreationFund model

The conceptual fund contains a segregated economic account per Universe, but the first implementation may derive those accounts from ledger projections.

Genesis allocation is configurable. The Council-approved initial reference profile is R$10 per Universe when real economic mode is explicitly enabled.

### 15.2 Default conservative risk profile

Initial configurable reference values:

- structural reserve: 50%;
- max operational capital: 50%;
- max risk per action: 10% of Universe NAV;
- max simultaneous exposure: 30%;
- daily stop: 10%;
- cumulative drawdown stop: 20%;
- no debt;
- no margin;
- no leverage;
- no negative balance;
- no automatic recapitalization after economic suspension.

These are policy defaults, not immutable constitutional constants.

As NAV grows, allowed risk percentage should decline rather than scale linearly upward.

### 15.3 Ledger states

Economic movements conceptually follow:

```text
AVAILABLE
→ RESERVED
→ COMMITTED
→ SETTLING
→ SETTLED
→ PROFIT / LOSS
```

If the external outcome is uncertain:

```text
SETTLING
→ UNKNOWN
→ RECONCILIATION_REQUIRED
```

Associated capital remains frozen while outcome is unknown. Equivalent material action must not be blindly retried.

Simulated or paper profit must never be booked as real cash.

### 15.4 Economic suspension

A Universe that reaches the configured economic loss boundary becomes `ECONOMIC_SUSPENDED` for real-capital deployment.

It is not deleted. It may continue to:

- perceive;
- research;
- learn;
- simulate;
- critique;
- contribute;
- compete in shadow mode.

It does not receive automatic new real capital. Recapitalization requires an explicit Creator-governed future mechanism.

## 16. Capability execution and reconciliation

The existing capability runtime remains the sole material effect path.

```text
Mission
→ AgentRuntime
→ CapabilityIntent
→ CapabilityRuntime
→ CapabilityGateway
→ Adapter/provider
→ Result
```

No provider may execute material effects outside that boundary.

Where the current runtime marks uncertain outcomes, the opportunity/economic layer must respect that uncertainty and reconcile before settlement or equivalent retry.

Provider failure must never be interpreted as proof that no external effect happened.

## 17. Learning and evolution

Learning may adjust:

- sensor preference;
- provider preference;
- detector weights;
- retrieval strategy;
- exploration/exploitation balance;
- thesis templates;
- critic intensity;
- skill/tool selection;
- memory compaction.

Learning may **not** self-expand:

- Creator constraints;
- authorization gates;
- risk ceilings beyond policy;
- CapabilityGateway authority;
- audit requirements;
- reconciliation requirements;
- external effect boundaries;
- security policy.

The basic loop is:

```text
experience
→ outcome
→ self-critique
→ peer critique
→ candidate improvement
→ replay/shadow validation
→ promote or retire
```

## 18. Provider adoption lifecycle

New MCPs/plugins/providers follow:

```text
discover
→ inspect origin/license/security
→ capability mapping
→ sandbox/shadow test
→ evidence review
→ certify
→ register as provider
```

No provider is automatically trusted because it appears in a registry or repository.

The Creation owns provider interfaces. External repositories must not be forked into the core unless there is a specific justified need that adapters cannot satisfy.

## 19. Kill switches and scope isolation

Three scopes remain conceptually required:

1. Universe-level economic suspension/kill switch;
2. domain/provider-level kill switch;
3. global fund/material-execution kill switch.

A failure in one domain should not automatically halt unrelated low-risk work unless the global boundary is triggered.

## 20. Implementation strategy approved by the engineering council

Externally, implementation is delivered as **one consolidated PR**.

Internally, it is executed as sequential TDD gates with independent verification and commits.

Recommended order:

1. Freeze and verify baseline.
2. Restore/reconcile the canonical 12 Universes idempotently.
3. Generalize Mission origin with a database-enforced exclusive origin invariant.
4. Add `Opportunity`, `OpportunityThesis`, `OpportunityLease` and `EconomicLedgerEntry`.
5. Implement opportunity discovery/qualification and thesis competition using the existing runtime patterns.
6. Connect selected opportunity to Mission creation.
7. Integrate economic reservation, settlement and reconciliation with capability execution outcomes.
8. Expand stable logical web/browser/research capabilities and add external providers behind adapters.
9. Add adaptive provider/sensor/detector learning using Chronicle and UniverseMemory.
10. Run migration, concurrency, idempotency, reconciliation, creator-isolation, regression and full-stack gates before PR merge.

The central implementation rule is:

> Stabilize `Opportunity → Mission → Capability execution → Reconciliation → Ledger` before integrating many external providers.

This prevents a large sensor ecosystem from being built before the system can safely decide, execute, account and learn.

## 21. Migration strategy

The current main-line migration sequence must be treated as canonical. New migration work should continue from the current head rather than reusing historical migration numbering that no longer belongs to the active chain.

The migration must support:

- fresh database creation;
- upgrade of an existing current database;
- idempotent canonical Universe reconciliation;
- Mission-origin constraint enforcement;
- executive lease uniqueness;
- foreign-key integrity across Creator, Universe, Mission and Opportunity state;
- safe rollback where structurally feasible.

## 22. Test and verification requirements

Minimum mandatory verification:

### Universe restoration
- all 12 canonical codes exist exactly once;
- repeated seed/reconciliation is idempotent;
- active Agent availability is deterministic;
- existing Creator isolation remains intact.

### Mission origin
- Creator Inception path continues to work unchanged;
- Opportunity path works without fabricated Inception;
- both origin fields set is rejected;
- neither origin field set is rejected.

### Opportunity and competition
- deterministic fingerprint behavior;
- duplicate clustering behavior;
- multiple research theses allowed;
- no more than one active executive lease per opportunity;
- lease race/concurrency test at database level;
- expired/released lease can be replaced according to policy.

### Economic ledger
- reservation cannot exceed permitted available capital;
- settlement is append-oriented and auditable;
- unknown outcomes freeze associated exposure;
- simulated outcomes do not affect real cash projection;
- drawdown and NAV projection calculations are deterministic;
- economic suspension blocks further real-capital reservation.

### Capability integration
- unauthorized capability remains denied;
- allowed actions within envelope proceed without repeated Creator approval;
- uncertain at-most-once external effects are not blindly retried;
- provider replacement does not change Universe/Mission semantics.

### Regression
- existing Creator → Inception → Mission flow;
- current worker lifecycle;
- existing workspace capability;
- existing web capability;
- existing PROTO capability;
- Chronicle integrity;
- memory behavior;
- lint/type/full test suite.

## 23. Architectural invariants

These invariants are mandatory:

1. Opportunity does not grant authority.
2. Capital availability does not grant authority.
3. Winning a competition does not grant authority.
4. Read access does not grant action authority.
5. Lower layers may restrict authority but never expand it.
6. DENY wins.
7. Material external effects pass through the existing capability execution boundary.
8. One active executive lease per opportunity.
9. Uncertain outcome blocks equivalent material re-execution until reconciliation.
10. Settled real evidence is required before economic profit/loss becomes final.
11. Simulated profit is not cash.
12. Learning cannot self-expand governance or economic ceilings.
13. Sector is context, not a Universe prison.
14. Shared evidence does not erase independent cognition.
15. Creator-origin and Opportunity-origin Missions share the same downstream runtime.

## 24. Final approved architecture

```text
WORLD
  ↓
Sensors / APIs / Web / MCP / Plugins / PROTO
  ↓
12 Universe Perception Cells
  ↓
Opportunity
  ↓
Competing / collaborative theses
  ↓
Selected thesis + executive lease
  ↓
Mission(origin=OPPORTUNITY)
  ↓
Existing authorization/autonomy envelope
  ↓
Existing AgentRuntime
  ↓
Existing CapabilityRuntime / CapabilityGateway
  ↓
External effect
  ↓
Reconciliation
  ↓
EconomicLedgerEntry + Chronicle
  ↓
UniverseMemory / learning
  ↺
```

The Creator path remains in parallel:

```text
CREATOR MESSAGE
→ Inception
→ Mission(origin=CREATOR_INCEPTION)
→ same downstream runtime
```

## 25. Council verdict

**Architecture: PASS.**

The approved implementation direction is to evolve the current Creation kernel rather than build a parallel system. The 12 Universes become autonomous cognitive/economic actors on top of existing Mission, Agent, memory, capability and Chronicle infrastructure. Only the minimum persistent opportunity and ledger state is added. External tools remain replaceable providers. Autonomous flow is enabled through persistent scoped mission envelopes, with reconciliation and governance preserved.

The next step after Creator review of this specification is a Superpowers implementation plan written from this document, using TDD and one consolidated PR.