# The Creation OS — Mobile PWA Finalization Design

**Date:** 2026-09-26  
**Status:** Approved design pending written-spec review  
**Owner:** Creator  
**Scope:** Full application audit, production hardening, and installable phone/tablet experience

## 1. Intent

Finish The Creation OS as a production-quality application that preserves the current living-DEUS dashboard while making the same application installable and usable on phones and tablets. The work must reuse the existing React frontend, FastAPI backend, API contracts, authentication model, Docker topology, and CI workflows. It must not introduce a second frontend, a native business-logic layer, or duplicated domain behavior.

Success means the Creator can authenticate, converse with DEUS, inspect system health, review decisions, and recover from connection failures on desktop, tablet, and phone through one responsive application. The installed experience must launch in its own window, respect device safe areas and virtual keyboards, and update without caching private operational data.

## 2. Selected Approach

Implement a standards-based Progressive Web App (PWA) on top of the existing Vite/React frontend.

This approach was selected because it:

- keeps one codebase and one deployment surface;
- installs directly from a supported browser;
- avoids a new Capacitor, Android, or iOS project layer;
- preserves all current API and security boundaries;
- remains compatible with a future store wrapper if that becomes a separate requirement.

Store packaging and native-only integrations are excluded from this phase.

## 3. Architecture

### 3.1 Existing boundaries remain authoritative

- `frontend/src/App.tsx` remains the authenticated workspace owner.
- `frontend/src/CreatorConsole.tsx` remains the DEUS conversation surface.
- `frontend/src/DecisionsPanel.tsx` remains the Creator decision workflow.
- `frontend/src/Cosmos.tsx` remains the living visual presence.
- `frontend/src/api.ts` and `frontend/src/types.ts` remain the frontend API contract.
- The FastAPI application remains the sole source of operational and identity data.
- Existing reverse-proxy and Docker deployment topology remain unchanged except for serving PWA assets and headers when required.

No backend schema or endpoint change is planned unless audit evidence proves that a correctness or security defect requires one.

### 3.2 PWA shell

The frontend will add:

- a web application manifest with product identity, theme/background colors, standalone display, portrait/landscape compatibility, and appropriate icons;
- installable icon assets that remain legible at maskable and conventional sizes;
- a minimal service worker registered from the current entry point;
- an update lifecycle that never silently replaces an active session mid-operation;
- install and offline status semantics exposed accessibly when relevant.

The service worker may cache only versioned static shell assets required to start the interface. It must not cache authentication responses, API payloads, conversations, Chronicle events, SSE streams, mission data, decision data, or any request carrying authorization material. API traffic remains network-only.

### 3.3 Responsive interaction model

The living DEUS presence remains the visual center on large screens. On tablets and phones:

- the canvas scales without horizontal overflow or clipping essential controls;
- conversation remains the primary action and moves with the visual viewport when the keyboard opens;
- Decisions and System Vitals become touch-safe inset drawers;
- drawer content owns its internal scroll while the background remains stable;
- all actions meet a minimum 44 by 44 CSS-pixel touch target where practicable;
- safe-area insets are respected on all four sides;
- portrait and landscape layouts preserve access to authentication, conversation, decisions, logout, status, and retry;
- hover remains an enhancement only; every capability has touch and keyboard access;
- reduced-motion mode suppresses ambient movement without hiding operational state.

Phone layouts prioritize DEUS, the current state, and conversation. Dense telemetry stays in System Vitals and is not duplicated on the primary surface.

### 3.4 Authentication and sensitive data

Authentication behavior remains canonical. Password fields stay masked by default and support password managers and paste. Session expiry returns to Creator Access with an accessible explanation.

The PWA will not persist API payloads or secrets beyond the application’s existing session behavior. Service-worker logs, cache keys, manifest metadata, URLs, notifications, and install prompts must not expose credentials or sensitive operational content.

### 3.5 Connectivity and update behavior

The application must distinguish:

- initial loading;
- connected/live;
- reconnecting/resynchronizing;
- temporarily offline;
- authentication required;
- unrecoverable request failure with Retry.

The static shell may open while offline, but protected content must show an honest unavailable state rather than stale operational data. When a new frontend version is available, the application may apply it automatically only before authentication or after a safe reload. During an authenticated active session it must offer a non-disruptive reload action.

## 4. Quality Audit

The audit covers:

- repository state, branch ancestry, uncommitted work, and migration consistency;
- frontend type checking, unit tests, production build, bundle behavior, and browser errors;
- backend formatting, linting, typing, unit/integration tests, migrations, authorization, and error contracts;
- Docker Compose configuration and health checks for canonical local and production profiles;
- authentication, session expiry, SSE reconnection, decision mutation, retry, and empty/error states;
- dependency and static security analysis already represented in CI, plus targeted source review for exposed secrets, unsafe caching, native dialogs, and insecure storage;
- accessibility against WCAG 2.2 AA for semantics, names, focus, contrast, keyboard, touch, and reduced motion;
- performance risks including unnecessary canvas work, duplicate requests, layout shifts, and oversized cached assets;
- deployment configuration for correct manifest, service-worker scope, cache headers, and SPA fallback.

Findings within the approved scope will be fixed in the same delivery. A finding that requires an irreversible data migration, external credential, commercial account, or new product decision will be recorded as an explicit external blocker rather than guessed.

## 5. Verification Matrix

### 5.1 Automated gates

- `git diff --check`
- strict Frontend Design Premium static audit
- TypeScript check and Vite production build
- frontend unit tests
- complete Playwright E2E suite
- dedicated PWA manifest/service-worker tests
- Python Ruff, mypy, and pytest suites
- Alembic upgrade to head on a clean PostgreSQL database
- Docker Compose configuration and health checks
- dependency audit and applicable security workflows

### 5.2 Browser and device coverage

Required viewport checks:

- desktop: 1440 × 900;
- tablet landscape: 1024 × 768;
- tablet portrait: 768 × 1024;
- phone portrait: 390 × 844;
- compact phone: 360 × 800;
- phone landscape: 844 × 390.

Each applicable viewport must exercise authentication, dashboard load, conversation controls, both drawers, close/Escape behavior, failure recovery, long content, virtual-keyboard-safe layout, and horizontal-overflow absence. Chromium is the automated baseline; browser-specific PWA limitations must be documented honestly.

### 5.3 Accessibility states

Verification includes keyboard-only navigation, visible focus, accessible names and live regions, 200% zoom where supported, reduced motion, high-contrast resilience, and touch-target inspection.

## 6. Delivery and Integration

Implementation will occur on an isolated feature branch/worktree or the existing isolated dashboard branch after reconciling it with the latest main. Commits will remain reviewable by concern. A pull request will include the audit evidence and exact verification commands. Merge occurs only after required CI and review gates pass.

The delivery is considered complete only when:

1. the responsive PWA behavior is implemented;
2. project-owned automated tests pass;
3. the documented browser/device matrix is exercised;
4. blocking audit findings are resolved;
5. the PR is open and CI is green;
6. the change is merged into `main` when repository permissions and branch protection allow it;
7. any remaining external deployment or credential dependency is stated precisely.

## 7. Non-goals

- App Store or Play Store submission.
- Capacitor, React Native, Flutter, or a second native codebase.
- Background collection of device data.
- Offline mutation, offline conversation, or cached operational telemetry.
- New backend business features unrelated to correctness, security, accessibility, or mobile usability.
- Visual replacement of the approved living-DEUS dashboard.

## 8. Product Decisions Fixed by This Specification

- The mobile artifact is an installable PWA.
- One responsive React application serves desktop, tablet, and phone.
- DEUS conversation remains the primary surface.
- Decisions and System Vitals remain contextual drawers.
- Only static shell assets may be cached.
- Operational data is network-only and never presented as current while offline.
- WCAG 2.2 AA is the accessibility target.
- Existing backend APIs and domain boundaries are preserved.
