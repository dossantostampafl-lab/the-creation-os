# The Creation OS Mobile PWA Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish The Creation OS as an audited, production-quality, installable PWA that preserves the current living-DEUS experience across desktop, tablet, and phone.

**Architecture:** Extend the existing Vite/React frontend with standards-based PWA metadata, a static-shell-only service worker, and a small status component; preserve the FastAPI API and current domain boundaries. Harden responsive behavior in the existing layout and verify deployment headers, security, accessibility, and all project-owned test suites without introducing a native application layer.

**Tech Stack:** React 19, TypeScript 7, Vite 8, vanilla Service Worker API, Playwright, Vitest, FastAPI, pytest, Nginx, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-26-mobile-pwa-finalization-design.md`

## Global Constraints

- One responsive React application must serve desktop, tablet, and phone.
- Existing backend APIs, authentication, and domain boundaries remain authoritative.
- Do not introduce Capacitor, React Native, Flutter, or a second frontend.
- Only versioned static shell assets may be cached; `/api/`, authorization-bearing requests, SSE, conversations, decisions, and telemetry are network-only.
- The offline shell must never present stale operational data as current.
- The visual focal point remains DEUS; dense telemetry remains inside System Vitals.
- Accessibility target is WCAG 2.2 AA.
- Required viewports are 1440×900, 1024×768, 768×1024, 390×844, 360×800, and 844×390.
- Use test-first implementation and commit each independently reviewable task.

## Review Focus

- An authenticated session loses connectivity: preserve the shell, mark it offline, and do not display cached API data as current; covered by Task 3 E2E.
- A service-worker update arrives during active use: show a non-disruptive reload action instead of replacing the session; covered by Task 3 unit/E2E tests.
- A virtual keyboard or safe-area inset reduces the phone viewport: keep the conversation control reachable without horizontal overflow; covered by Task 4 viewport tests.
- Long mission, event, and provider text appears in a drawer: keep controls visible and scrolling owned by the drawer; covered by Task 4 long-content tests.
- Authentication expires while installed: return to Creator Access without leaking secret values or stale content; covered by Task 6 full-flow tests.

---

### Task 1: Establish the Auditable Baseline

**Files:**
- Create: `docs/superpowers/audits/2026-09-26-mobile-pwa-baseline.md`
- Inspect: `frontend/package.json`
- Inspect: `backend/pyproject.toml`
- Inspect: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: approved mobile PWA specification and current feature branch.
- Produces: a dated evidence record containing branch SHA, tool versions, commands, pass/fail counts, and environment limitations.

- [ ] **Step 1: Reconcile repository state without discarding work**

Run `git status --short --branch`, `git log --oneline --decorate -10`, `git diff --check`, and fetch the latest remote refs. Record the current SHA and relationship to `origin/main`.

- [ ] **Step 2: Run the available baseline gates**

Run `npm run build && npm test` in `frontend`; create an isolated Python virtual environment, install `backend[dev]`, then run `ruff check .`, `mypy app`, and `pytest -q` in `backend`. Run `docker compose config --quiet` when Docker is available.

- [ ] **Step 3: Write the audit record**

Record exact results rather than inferred status. Classify failures as product defect, missing local dependency, unavailable infrastructure, or external credential requirement.

- [ ] **Step 4: Commit the baseline**

```bash
git add docs/superpowers/audits/2026-09-26-mobile-pwa-baseline.md
git commit -m "docs: record mobile PWA audit baseline"
```

### Task 2: Add Installable PWA Identity

**Files:**
- Create: `frontend/public/manifest.webmanifest`
- Create: `frontend/public/icons/icon-192.png`
- Create: `frontend/public/icons/icon-512.png`
- Create: `frontend/public/icons/maskable-512.png`
- Modify: `frontend/index.html`
- Create: `frontend/e2e/pwa.spec.ts`

**Interfaces:**
- Consumes: runtime colors and product identity from `DESIGN.md`.
- Produces: `/manifest.webmanifest` and declared icons linked from the application document.

- [ ] **Step 1: Write failing manifest tests**

Add Playwright tests asserting that the document links `/manifest.webmanifest`, viewport includes `viewport-fit=cover`, the manifest uses name `The Creation OS`, `display: "standalone"`, `start_url: "/"`, theme/background colors from `DESIGN.md`, and 192/512/maskable icons return non-empty PNG responses.

- [ ] **Step 2: Verify the tests fail**

Run `npx playwright test e2e/pwa.spec.ts --project=chromium`. Expected: missing manifest or icon assertions fail.

- [ ] **Step 3: Implement metadata and icon assets**

Add the manifest, conventional and maskable icons derived from the approved DEUS visual language, the manifest link, Apple touch icon, `viewport-fit=cover`, and standalone/mobile-capable metadata. Keep `robots` restrictions unchanged.

- [ ] **Step 4: Verify manifest behavior**

Run `npm run build`, `npm test`, and `npx playwright test e2e/pwa.spec.ts --project=chromium`. Expected: all pass and built `dist` includes the manifest and icons.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/public frontend/e2e/pwa.spec.ts
git commit -m "feat(frontend): add installable Creation PWA identity"
```

### Task 3: Implement Safe Service-Worker and Update Lifecycle

**Files:**
- Create: `frontend/public/sw.js`
- Create: `frontend/src/pwa.ts`
- Create: `frontend/src/pwa.test.ts`
- Create: `frontend/src/PwaStatus.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/e2e/pwa.spec.ts`

**Interfaces:**
- Consumes: `registerPwa(options?: PwaRegistrationOptions): Promise<ServiceWorkerRegistration | null>` from `frontend/src/pwa.ts`.
- Produces: `PwaStatus` UI, `pwa:update-available` event handling, network status, and a service worker that caches only approved static shell resources.

- [ ] **Step 1: Write failing unit tests for registration and updates**

Test `registerPwa` for unsupported browsers, successful registration, waiting-worker update notification, `controllerchange`, and registration failure without an unhandled rejection.

- [ ] **Step 2: Write failing service-worker contract tests**

Extend `pwa.spec.ts` to assert `/sw.js` exists, contains an explicit `/api/` network-only guard, ignores non-GET and authorization-bearing requests, supports `SKIP_WAITING`, and uses a versioned static cache.

- [ ] **Step 3: Verify tests fail**

Run `npm test -- src/pwa.test.ts` and `npx playwright test e2e/pwa.spec.ts --project=chromium`. Expected: missing module/service-worker failures.

- [ ] **Step 4: Implement registration and safe caching**

Implement `registerPwa` and `sw.js`. Cache the navigation shell and immutable same-origin static assets only; fetch navigation network-first with an offline shell fallback; never cache API, SSE, non-GET, cross-origin, or authorization-bearing requests.

- [ ] **Step 5: Implement `PwaStatus`**

Render an accessible live status for offline mode and an update banner with `Reload now`. The reload action posts `SKIP_WAITING` to the waiting worker and reloads only after `controllerchange`; it must not silently interrupt an active session.

- [ ] **Step 6: Add E2E for offline and update states**

Assert that an offline event produces honest offline copy, no stale-current claim, and recovery on an online event. Dispatch the update event and assert that the reload action is visible and keyboard reachable.

- [ ] **Step 7: Verify and commit**

Run `npm run build`, `npm test`, and `npx playwright test e2e/pwa.spec.ts --project=chromium`.

```bash
git add frontend/public/sw.js frontend/src/pwa.ts frontend/src/pwa.test.ts frontend/src/PwaStatus.tsx frontend/src/main.tsx frontend/src/App.tsx frontend/src/styles.css frontend/e2e/pwa.spec.ts
git commit -m "feat(frontend): add safe PWA lifecycle"
```

### Task 4: Harden Phone and Tablet Interaction

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/CreatorConsole.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/CreatorConsole.css`
- Modify: `frontend/e2e/living-operations.spec.ts`
- Modify: `frontend/e2e/creator-console.spec.ts`

**Interfaces:**
- Consumes: existing edge triggers, drawers, conversation form, connection state, and `PwaStatus`.
- Produces: touch-safe responsive layouts across the required viewport matrix without changing API types.

- [ ] **Step 1: Write failing viewport-matrix tests**

For 1024×768, 768×1024, 390×844, 360×800, and 844×390, assert no document-level horizontal overflow, visible Creator Access or conversation control, reachable Decisions/Vitals triggers, and drawers contained within the visual viewport.

- [ ] **Step 2: Write failing interaction and long-content tests**

Use long mission/provider/event strings. Assert drawer-owned scrolling, 44×44 primary touch targets, focus restoration after drawer close, Escape behavior, and conversation visibility after a viewport-height reduction that represents a virtual keyboard.

- [ ] **Step 3: Verify tests fail for current CSS**

Run the targeted Playwright tests and capture the failing viewport/state names.

- [ ] **Step 4: Implement responsive layout hardening**

Use `100dvh` with safe fallback, all four `env(safe-area-inset-*)` values, visual-viewport-safe console placement, phone/landscape breakpoints, drawer scroll ownership, truncation/wrapping rules, and touch targets without hiding controls or duplicating telemetry.

- [ ] **Step 5: Verify keyboard and reduced motion**

Run the targeted E2E suite with keyboard-only drawer use and reduced-motion emulation. Assert the operational state remains available as DOM text when animation is suppressed.

- [ ] **Step 6: Verify and commit**

Run `npm run build`, `npm test`, and both Playwright suites.

```bash
git add frontend/src/App.tsx frontend/src/CreatorConsole.tsx frontend/src/styles.css frontend/src/CreatorConsole.css frontend/e2e
git commit -m "feat(frontend): harden tablet and phone experience"
```

### Task 5: Harden PWA Delivery at the Reverse Proxy

**Files:**
- Modify: `frontend/nginx.conf`
- Modify: `frontend/nginx.render.conf`
- Create: `backend/tests/test_pwa_deployment_invariants.py`

**Interfaces:**
- Consumes: `/sw.js`, `/manifest.webmanifest`, and hashed `/assets/` from Tasks 2–3.
- Produces: consistent headers and cache policy in local/cloud Nginx configurations.

- [ ] **Step 1: Write failing deployment-invariant tests**

Assert both Nginx files serve `sw.js` with revalidation/no-cache, the manifest with a bounded cache lifetime and correct MIME type, hashed assets as immutable, and SPA navigation through `index.html`; retain existing CSP and security headers.

- [ ] **Step 2: Verify the test fails**

Run `pytest -q tests/test_pwa_deployment_invariants.py`. Expected: missing PWA location/header assertions fail.

- [ ] **Step 3: Implement matching Nginx policies**

Add explicit locations for service worker, manifest, and hashed assets without changing `/api/`, health checks, CSP, or server topology.

- [ ] **Step 4: Verify and commit**

Run the targeted pytest file, `docker compose config --quiet`, and frontend build.

```bash
git add frontend/nginx.conf frontend/nginx.render.conf backend/tests/test_pwa_deployment_invariants.py
git commit -m "fix(deploy): enforce safe PWA cache policy"
```

### Task 6: Execute the Full Product and Accessibility Audit

**Files:**
- Create: `docs/superpowers/audits/2026-09-26-mobile-pwa-final.md`
- Modify when evidence requires: files owning the failing behavior only.
- Test when evidence requires: the nearest existing unit/E2E/integration suite.

**Interfaces:**
- Consumes: complete implementation from Tasks 2–5.
- Produces: strict static-audit evidence and regression tests for every blocking finding.

- [ ] **Step 1: Run the strict premium UI audit**

Run `python /root/.codex/plugins/cache/openai-curated-remote/frontend-design-premium/1.4.0/skills/frontend-design-premium/scripts/audit_project.py . --mode strict` from the repository root and preserve its JSON output in the audit report.

- [ ] **Step 2: Run targeted anti-pattern and security searches**

Search application code for native dialogs, non-semantic click handlers, unsafe secret persistence, API/service-worker caching, missing accessible names, hidden scrollbars, unbounded tables/lists, and credentials in URLs/logging. Exclude dependencies and generated build artifacts.

- [ ] **Step 3: Fix each blocking finding test-first**

For every product defect, add a focused failing test in the owning suite, reproduce it, implement the smallest correction, and rerun the focused test. Do not broaden features or refactor unrelated code.

- [ ] **Step 4: Exercise auth/session/failure states**

Verify invalid login, successful login, expired session, API unavailable with Retry, inference unconfigured, SSE resync/error, empty decisions, mutation failure, offline shell, and recovery.

- [ ] **Step 5: Write and commit the final audit**

Document exact findings, fixes, commands, counts, and any external-only limitation.

```bash
git add docs/superpowers/audits/2026-09-26-mobile-pwa-final.md frontend backend
git commit -m "docs: record final mobile PWA audit"
```

### Task 7: Run the Release Gauntlet and Integrate

**Files:**
- Modify if evidence requires: `.github/workflows/ci.yml`
- Modify if evidence requires: `.github/workflows/security.yml`
- Modify: `CHANGELOG_DECISIONS.md`
- Modify: `PROJECT_STATE.yaml`

**Interfaces:**
- Consumes: all task commits and final audit evidence.
- Produces: a reviewable PR, green required checks, and an integrated `main` commit when permissions allow.

- [ ] **Step 1: Run complete local verification**

Run `git diff --check`; frontend build, unit, and full Playwright suites; backend Ruff, mypy, pytest, and Alembic upgrade; Rust checks for any touched gateway code; Compose configuration and stack health checks when Docker is available.

- [ ] **Step 2: Capture visual evidence once per representative class**

Capture the same built application at desktop 1440×900, tablet portrait 768×1024, and phone portrait 390×844. Inspect the captures for clipping, overflow, safe-area collision, drawer reachability, contrast, and content duplication.

- [ ] **Step 3: Update release records**

Record the PWA/mobile state, validation evidence, and any honest external limitation in `CHANGELOG_DECISIONS.md` and `PROJECT_STATE.yaml` without marking unavailable store packaging or credentials as complete.

- [ ] **Step 4: Request whole-branch review**

Review the branch against the approved spec, audit report, and diff. Resolve every blocking finding with a focused regression test and rerun the relevant gauntlet.

- [ ] **Step 5: Push and open the pull request**

Push the feature branch, open a PR containing summary, device matrix, security/cache contract, screenshots, and verification commands. Wait for required CI and security checks.

- [ ] **Step 6: Merge only when green**

Merge through the repository’s permitted strategy after required checks pass, then verify the resulting `main` SHA and post-merge workflow status. If repository protection or credentials block integration, report that exact external blocker and leave the green PR ready to merge.
