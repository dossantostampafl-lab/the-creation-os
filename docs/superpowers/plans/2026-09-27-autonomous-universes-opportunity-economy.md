# Autonomous Universes, Opportunity Fabric and Economic Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the canonical 12 Universes, autonomous opportunity-to-Mission flow, economic ledger, bounded autonomy, and plug-in perception providers while reusing the current THE CREATION OS runtime and keeping delivery in one consolidated PR.

**Architecture:** Extend the existing `Universe`, `Mission`, `AgentRuntime`, `CapabilityRuntime`, `CapabilityGateway`, `UniverseMemory`, Chronicle and projection paths. Add only four persistent domain objects (`Opportunity`, `OpportunityThesis`, `OpportunityLease`, `EconomicLedgerEntry`) plus the minimal Mission-origin schema change. External MCPs/crawlers/browsers remain replaceable providers behind existing capabilities rather than new services.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, PostgreSQL, Alembic, Pydantic v2, pytest/pytest-asyncio, Ruff, mypy, existing Redis/worker runtime.

**Spec:** `docs/superpowers/specs/2026-09-27-autonomous-universes-opportunity-economy-design.md`

## Global Constraints

- One consolidated PR; implementation is split into independently testable commits/gates.
- Reuse the current kernel before creating new infrastructure.
- Preserve existing Creator-Inception Mission flow without behavior regression.
- Exactly one Mission origin: Creator Inception XOR Opportunity.
- Lower layers may restrict authority but never expand it; DENY remains dominant.
- Capital availability never grants authority.
- No blind retry after uncertain external outcomes; reconcile first.
- Simulated/paper results never become settled real capital.
- Perception Cell remains a composition, not a service/table.
- MCPs/plugins/crawlers/browser tools are replaceable providers, not architectural layers.
- Public read-only perception must preserve the existing SSRF/access-control protections.
- Start schema evolution from migration `0010_*`; do not resurrect historical migration numbering.
- No new broker, ActionOrchestrator, EconomicRuntime, second CapabilityGateway, or twelve separate runtimes.

## Review Focus

1. **Mission origin integrity:** existing Inception Missions continue to work, and database constraints reject both-null or both-set origins.
2. **Executive lease races:** concurrent contenders cannot obtain two active executive leases for one Opportunity.
3. **Economic uncertainty:** `AT_MOST_ONCE`/uncertain capability failure freezes related capital and forbids equivalent settlement/retry until reconciliation.
4. **Creator isolation:** Opportunity, theses, leases and ledger entries cannot cross Creator boundaries through IDs or projections.
5. **Web-provider safety:** adding search/crawl/extract/browser providers must not weaken public-address, redirect, host-scope or authorization checks already enforced by `web.py`.

---

## File Map

**Modify existing**
- `backend/app/admin/seed.py` — canonical 12 Universe catalog and minimal staffing.
- `backend/app/models/entities.py` — make `Mission.inception_id` nullable and add `opportunity_id` relationship/origin invariant surface.
- `backend/app/models/__init__.py` — export new models where required by metadata loading.
- `backend/app/repositories/domain.py` — reuse generic persistence/Chronicle patterns for opportunity/economic transactions.
- `backend/app/services/domain.py` — integrate selected Opportunity into the existing Mission/plan/task lifecycle.
- `backend/app/schemas/mission.py` — expose Mission origin without breaking current API shapes.
- `backend/app/capabilities/contracts.py` — add optional economic request metadata only if needed by material-cost capabilities; keep backward compatibility.
- `backend/app/capabilities/runtime.py` — economic reservation/settlement hooks around material capability execution.
- `backend/app/capabilities/web.py` — evolve from fetch-only to safe multi-action web perception without weakening SSRF controls.
- `backend/app/worker.py` — configure optional perception providers through the existing gateway bootstrap.
- `backend/app/config.py` — provider/economic policy configuration.
- `backend/app/projections/system.py` and `backend/app/projections/refresher.py` — expose derived economic/opportunity state.

**Create**
- `backend/app/models/opportunity.py` — `Opportunity`, `OpportunityThesis`, `OpportunityLease`.
- `backend/app/models/economy.py` — `EconomicLedgerEntry`.
- `backend/app/schemas/opportunity.py` — typed opportunity/thesis views/commands.
- `backend/app/schemas/economy.py` — typed economic projections.
- `backend/app/services/opportunity.py` — deterministic qualification, thesis submission, selection/lease, Mission handoff.
- `backend/app/services/economy.py` — append-only ledger operations and economic policy evaluation.
- `backend/app/capabilities/web_providers.py` — internal provider protocol and config-gated implementations/adapters; not a service.
- `backend/alembic/versions/0010_autonomous_universes_opportunity_economy.py` — schema migration and constraints.
- focused tests listed per task below.

---

### Task 1: Restore the canonical 12 Universes idempotently

**Files:**
- Modify: `backend/app/admin/seed.py`
- Create: `backend/tests/test_canonical_universe_seed.py`

**Interfaces:**
- Produces: `CANONICAL_UNIVERSES` containing the 12 approved codes, names, historical UUIDs and minimal Agent defaults.
- Preserves: existing `seed_universes() -> int` CLI contract.

- [ ] **Step 1: Write failing tests** asserting the seed contains exactly the 12 canonical codes, preserves the approved UUID mapping, activates every Universe, creates at least one active Agent per Universe, and is idempotent on a second run.
- [ ] **Step 2: Run** `cd backend && pytest tests/test_canonical_universe_seed.py -v` and confirm failure against the current 4-Universe seed.
- [ ] **Step 3: Implement** the canonical catalog in `seed.py`; reconcile existing rows by code, preserve matching records, create only missing rows, and never delete current data implicitly.
- [ ] **Step 4: Run** the targeted test and the existing Universe/Living Core tests.
- [ ] **Step 5: Commit** `feat: restore canonical twelve universes`.

### Task 2: Add the four persistent domain objects and Mission-origin constraint

**Files:**
- Create: `backend/app/models/opportunity.py`
- Create: `backend/app/models/economy.py`
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0010_autonomous_universes_opportunity_economy.py`
- Create: `backend/tests/test_autonomous_schema.py`

**Interfaces:**
- Produces classes: `Opportunity`, `OpportunityThesis`, `OpportunityLease`, `EconomicLedgerEntry`.
- `Mission` produces `origin_type: Literal["CREATOR_INCEPTION", "OPPORTUNITY"]` as a derived/application-level value; persistence remains XOR foreign keys.

- [ ] **Step 1: Write failing schema tests** for tables, foreign keys, Creator ownership, unique Opportunity fingerprint scope, and Mission XOR origin.
- [ ] **Step 2: Add an integration test** that inserts valid Creator-Inception and Opportunity Missions and rejects both-null/both-set origins at DB level.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_autonomous_schema.py -v` and confirm failure.
- [ ] **Step 4: Implement models and Alembic `0010`** with a database `CHECK` constraint equivalent to `(inception_id IS NULL) <> (opportunity_id IS NULL)`, active-executive-lease uniqueness using a PostgreSQL partial unique index, and append-oriented ledger fields from the spec.
- [ ] **Step 5: Verify migration both ways** on a disposable PostgreSQL DB: upgrade `0009 -> 0010`, inspect constraints, downgrade `0010 -> 0009`, then upgrade again.
- [ ] **Step 6: Run** targeted tests.
- [ ] **Step 7: Commit** `feat: add opportunity and economic persistence`.

### Task 3: Implement deterministic Opportunity creation and deduplication

**Files:**
- Create: `backend/app/schemas/opportunity.py`
- Create: `backend/app/services/opportunity.py`
- Modify: `backend/app/repositories/domain.py`
- Create: `backend/tests/test_opportunity_service.py`

**Interfaces:**
- `normalize_opportunity_fingerprint(*, sector: str, problem_or_gap: str, capture_mechanism: str, time_window: dict) -> str`
- `async def create_or_get_opportunity(repository: DomainRepository, *, creator_id: str, discovered_by_universe_id: str, sector: str, problem_or_gap: str, capture_mechanism: str, evidence_refs: list[str], time_window: dict, correlation_id: str) -> Opportunity`
- `async def submit_thesis(repository: DomainRepository, *, opportunity_id: str, universe_id: str, thesis: OpportunityThesisCreate, correlation_id: str) -> OpportunityThesis`

- [ ] **Step 1: Write failing tests** proving normalized-equivalent discoveries dedupe within one Creator but never across Creators.
- [ ] **Step 2: Add tests** requiring evidence refs and rejecting a thesis whose Universe belongs to a different Creator context/opportunity scope.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_opportunity_service.py -v`.
- [ ] **Step 4: Implement** deterministic fingerprinting, create-or-get behavior, thesis submission and Chronicle events using existing repository event patterns.
- [ ] **Step 5: Run** targeted tests.
- [ ] **Step 6: Commit** `feat: add opportunity discovery domain flow`.

### Task 4: Implement competition selection and database-backed leases

**Files:**
- Modify: `backend/app/services/opportunity.py`
- Create: `backend/tests/test_opportunity_competition.py`

**Interfaces:**
- `async def acquire_research_lease(...)-> OpportunityLease`
- `async def acquire_executive_lease(repository: DomainRepository, *, opportunity_id: str, thesis_id: str, universe_id: str, expires_at: datetime, correlation_id: str) -> OpportunityLease`
- `async def release_lease(...)-> OpportunityLease`
- `async def select_thesis(...)-> OpportunityThesis`

- [ ] **Step 1: Write a concurrency test** launching two transactions for executive lease acquisition and asserting exactly one succeeds.
- [ ] **Step 2: Write tests** for concurrent research leases, expired lease replacement, explicit release, and thesis selection that does not itself grant capability authority.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_opportunity_competition.py -v`.
- [ ] **Step 4: Implement** lease operations using database constraints/locking; do not rely on process-local locks.
- [ ] **Step 5: Run** tests under PostgreSQL at least twice to catch race flakiness.
- [ ] **Step 6: Commit** `feat: add opportunity competition leases`.

### Task 5: Convert a selected Opportunity into the existing Mission lifecycle

**Files:**
- Modify: `backend/app/services/domain.py`
- Modify: `backend/app/schemas/mission.py`
- Modify: `backend/app/services/opportunity.py`
- Create: `backend/tests/test_opportunity_mission_origin.py`

**Interfaces:**
- `async def create_mission_from_opportunity(repository: DomainRepository, *, creator_id: str, opportunity_id: str, thesis_id: str, executive_lease_id: str, title: str, objective: str, authorization: dict, correlation_id: str) -> Mission`
- Existing Creator `Inception -> Mission` service signatures remain unchanged.

- [ ] **Step 1: Write failing regression tests** proving current Creator-Inception Mission creation still returns the same states/relationships.
- [ ] **Step 2: Write failing Opportunity-origin tests** proving selected thesis + active executive lease can create one Mission, while absent/expired/wrong-Creator lease cannot.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_opportunity_mission_origin.py -v`.
- [ ] **Step 4: Implement** Opportunity-origin Mission creation by reusing current MissionPlan/MissionStep/Task distribution paths; do not introduce a second executor.
- [ ] **Step 5: Run** targeted tests plus existing Mission/Trinity tests.
- [ ] **Step 6: Commit** `feat: allow opportunity originated missions`.

### Task 6: Implement append-only economic ledger and projections

**Files:**
- Create: `backend/app/schemas/economy.py`
- Create: `backend/app/services/economy.py`
- Modify: `backend/app/projections/system.py`
- Modify: `backend/app/projections/refresher.py`
- Create: `backend/tests/test_economic_ledger.py`

**Interfaces:**
- `async def append_ledger_entry(repository: DomainRepository, *, creator_id: str, universe_id: str, mission_id: str | None, opportunity_id: str | None, entry_type: str, amount: Decimal, currency: str, status: str, external_reference: str | None, metadata: dict, correlation_id: str) -> EconomicLedgerEntry`
- `async def project_universe_economy(session: AsyncSession, *, creator_id: str, universe_id: str, currency: str) -> UniverseEconomicProjection`
- Projection fields: `available`, `reserved`, `committed`, `settling`, `settled_pnl`, `nav`, `drawdown`, `economic_status`.

- [ ] **Step 1: Write failing ledger tests** for genesis allocation, reserve, commit, settle-profit, settle-loss, unknown/reconciliation-required, and creator isolation.
- [ ] **Step 2: Write tests** proving paper/simulated entries cannot contribute to real `available`/`nav` projections.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_economic_ledger.py -v`.
- [ ] **Step 4: Implement** immutable append operations and derived projections; do not add a mutable account balance table.
- [ ] **Step 5: Add policy evaluation** for the spec defaults: reserve 50%, operational 50%, risk/action 10%, exposure 30%, daily stop 10%, cumulative drawdown 20%, no debt/margin/leverage/negative balance, configurable through settings/policy data.
- [ ] **Step 6: Run** targeted tests.
- [ ] **Step 7: Commit** `feat: add universe economic ledger`.

### Task 7: Bind economic reservation and reconciliation to the existing CapabilityRuntime

**Files:**
- Modify: `backend/app/capabilities/contracts.py`
- Modify: `backend/app/capabilities/runtime.py`
- Modify: `backend/app/kernel/agent_runtime.py` only if context plumbing is required
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_capability_runtime_integration.py`
- Create: `backend/tests/test_economic_capability_reconciliation.py`

**Interfaces:**
- Extend `CapabilityIntent` backward-compatibly with optional `economic: dict[str, Any] = {}` containing requested currency/max spend/risk metadata for material economic actions.
- Add function hooks from `services.economy`: `reserve_for_capability(...)`, `settle_capability_result(...)`, `mark_capability_uncertain(...)`.

- [ ] **Step 1: Write failing tests** proving capabilities without economic metadata retain current behavior.
- [ ] **Step 2: Write failing tests** proving a material priced action reserves before adapter execution, settles only after a confirmed result, and records `UNKNOWN/RECONCILIATION_REQUIRED` on uncertain `AT_MOST_ONCE` failure.
- [ ] **Step 3: Write the Review Focus test** proving an equivalent action cannot be re-reserved/retried while the prior effect is unresolved.
- [ ] **Step 4: Run** the two targeted runtime test files.
- [ ] **Step 5: Implement** hooks inside `CapabilityRuntime`; preserve its current durable invocation record and authorization ordering.
- [ ] **Step 6: Run** capability gateway/runtime/failure/chaos tests.
- [ ] **Step 7: Commit** `feat: reconcile economic effects through capability runtime`.

### Task 8: Encode Perception Cell profiles without adding a new runtime

**Files:**
- Modify: `backend/app/admin/seed.py`
- Modify: `backend/app/schemas/universe.py`
- Modify: `backend/app/services/domain.py` only if profile update persistence is needed
- Create: `backend/tests/test_universe_perception_profiles.py`

**Interfaces:**
- Store initial `preferred_sensors`, `detector_weights`, `exploration_strategy`, `inference_provider` and description inside existing Agent capabilities/Universe memory conventions.
- `def canonical_perception_profile(universe_code: str) -> dict[str, Any]`

- [ ] **Step 1: Write failing tests** for all 12 initial profiles and verify they are priors, not deny lists.
- [ ] **Step 2: Add a test** showing Engineering can request a commerce/web sensor and Business can request code/search when the Mission envelope permits it.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_universe_perception_profiles.py -v`.
- [ ] **Step 4: Implement** profiles using current capabilities/memory storage; do not create PerceptionCell tables/services.
- [ ] **Step 5: Run** targeted tests.
- [ ] **Step 6: Commit** `feat: seed autonomous universe perception profiles`.

### Task 9: Expand the existing Web capability into safe provider-backed perception

**Files:**
- Modify: `backend/app/capabilities/web.py`
- Create: `backend/app/capabilities/web_providers.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_capability_web.py`
- Create: `backend/tests/test_web_provider_selection.py`

**Interfaces:**
- Preserve `WebCapabilityAdapter.name == "web"`.
- Supported logical actions: `fetch`, `search`, `crawl`, `extract`; `fetch` remains direct and SAFE.
- `class WebProvider(Protocol): name: str; actions: frozenset[str]; async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> dict: ...`
- `select_web_provider(action: str, providers: Sequence[WebProvider], *, preferred: list[str] | None = None) -> WebProvider`.

- [ ] **Step 1: Extend existing web tests** so all current SSRF, redirect, host-scope and size-limit cases still pass for `fetch`.
- [ ] **Step 2: Write provider-selection tests** with fake providers covering action support, configured preference, fallback on provider-unavailable errors, and no provider case.
- [ ] **Step 3: Write tests** proving `search/crawl/extract` remain read-only and cannot bypass Mission host/domain restrictions where a URL/host is involved.
- [ ] **Step 4: Run** `cd backend && pytest tests/test_capability_web.py tests/test_web_provider_selection.py -v`.
- [ ] **Step 5: Implement** the provider protocol and routing inside the existing Web adapter. Keep provider configuration optional so a missing vendor credential never breaks direct `fetch`.
- [ ] **Step 6: Add config-gated HTTP/MCP provider clients only after their contract tests exist. Prioritize the approved candidates: Crawlee/Crawl4AI for local crawl/extract, Playwright MCP for dynamic observation, Firecrawl/Exa/Tavily/Brave for discovery, and Apify for specialized sources. Each client must map back to the stable logical actions; vendor names must not leak into Universe policy contracts.
- [ ] **Step 7: Run** targeted tests plus `test_capability_gateway.py` and runtime integration tests.
- [ ] **Step 8: Commit** `feat: add replaceable web perception providers`.

### Task 10: Add provider adoption/shadow evidence and learning without authority expansion

**Files:**
- Modify: `backend/app/services/opportunity.py`
- Modify: `backend/app/services/domain.py`
- Modify: `backend/app/models/entities.py` only if an existing memory metadata field cannot hold the data; prefer existing `UniverseMemory`.
- Create: `backend/tests/test_universe_learning.py`

**Interfaces:**
- `async def record_learning_episode(repository: DomainRepository, *, universe_id: str, source: str, strategy: dict, outcome: dict, correlation_id: str) -> UniverseMemory`
- Learning may update provider/sensor/detector weights only; it must not modify Mission authorization, Creator constraints, capability declarations or economic ceilings.

- [ ] **Step 1: Write failing tests** showing successful/failed outcomes adjust stored preferences but not authorization fields.
- [ ] **Step 2: Write a test** proving an experimental provider remains non-selected for material use until a shadow/certification flag is present.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_universe_learning.py -v`.
- [ ] **Step 4: Implement** learning persistence through `UniverseMemory` plus Chronicle events; no new learning service runtime.
- [ ] **Step 5: Run** targeted tests.
- [ ] **Step 6: Commit** `feat: learn perception preferences from outcomes`.

### Task 11: End-to-end autonomous opportunity flow and final regression gate

**Files:**
- Create: `backend/tests/test_autonomous_opportunity_e2e.py`
- Modify: `backend/app/projections/system.py`
- Modify: `backend/app/api/system_state.py` only to expose already-derived state if required by current dashboard/runtime consumers.
- Update: `PROJECT_STATE.yaml`, `FROZEN_DECISIONS.md`, `CHANGELOG_DECISIONS.md` only after tests prove implementation status.

**Interfaces:**
- E2E path: discovery -> Opportunity -> multiple theses -> selected thesis -> exclusive executive lease -> Opportunity-origin Mission -> authorization envelope -> AgentRuntime -> CapabilityRuntime -> confirmed/uncertain result -> ledger -> Chronicle -> UniverseMemory.

- [ ] **Step 1: Write the E2E test** using deterministic/fake inference and capability providers; assert no manual approval occurs for actions already inside the Mission envelope.
- [ ] **Step 2: Add failure branches** for denied capability, expired envelope, economic stop, lease loss, uncertain external result and reconciliation-before-retry.
- [ ] **Step 3: Run** `cd backend && pytest tests/test_autonomous_opportunity_e2e.py -v`.
- [ ] **Step 4: Run the full backend suite**: `cd backend && pytest -q`.
- [ ] **Step 5: Run static gates**: `cd backend && ruff check app tests` and `cd backend && mypy app`.
- [ ] **Step 6: Run migration verification** on fresh DB and existing `0009` DB; run worker/compose smoke if the repository CI workflow defines it.
- [ ] **Step 7: Update canonical status docs** only with evidence actually obtained; keep `DESIGN_APPROVED`, `IMPLEMENTED`, `TESTED`, and `VERIFIED_OPERATIONAL` distinct.
- [ ] **Step 8: Commit** `test: verify autonomous universes end to end`.

---

## Whole-PR Review Gate

Before opening the PR, verify:

- no second runtime/gateway/orchestrator was introduced;
- current Creator conversation/Inception flow is unchanged except for compatible Mission-origin fields;
- the 12 Universes are canonical, active and minimally staffed;
- every real-capital movement is ledger-backed;
- every material external effect still crosses `CapabilityRuntime -> CapabilityGateway`;
- uncertain effects cannot be blindly retried;
- provider failures degrade safely and direct `web.fetch` retains existing SSRF defenses;
- no provider/vendor name appears in Universe authority rules;
- full pytest, Ruff and mypy gates pass;
- migration upgrade/downgrade and fresh-install paths pass;
- the PR contains the implementation as one coherent change set with reviewable commits.

## Recommended execution method

Use **subagent-driven development** for implementation: Tasks 2, 4, 7, 9 and 11 contain schema/concurrency/external-effect failure modes where an independent reviewer after each task materially reduces integration risk. Keep all work on the single implementation branch and open only one consolidated PR after the whole-branch verification gate.
