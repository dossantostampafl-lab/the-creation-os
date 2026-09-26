# UX Contract

## Product context

- Audience: authenticated sovereign Creator.
- Primary jobs: converse with DEUS, decide Inceptions, authorize missions, inspect system health.
- Active locale: English UI; browser locale formats Chronicle time.
- Accessibility target: WCAG 2.2 AA.

## Sources and visual contract

The runtime API types in `frontend/src/types.ts` and request behavior in `frontend/src/api.ts` are authoritative. `DESIGN.md` records the visual rationale; `frontend/src/styles.css` and `frontend/src/CreatorConsole.css` own runtime tokens and component treatment.

## Canonical UI map

| Capability | Owner | Verification |
|---|---|---|
| Creator authentication | `App.tsx` login form | Playwright login success/failure |
| Conversation | `CreatorConsole.tsx` | Playwright send, voice, proposal flows |
| Decisions | `DecisionsPanel.tsx` | confirmation and error-path E2E |
| System inspection | `App.tsx` System Vitals drawer | operational-state E2E |
| Scrollbar | global CSS plus drawer/message exceptions | responsive browser check |

## Component behavior

Buttons preserve geometry through disabled/busy states and expose visible focus. Inputs are labeled; the secret input is masked by default and can be revealed. The message textarea does not resize, grows to its content limit, and ignores Enter submission during IME composition.

## Navigation and overlays

The document title is `The Creation OS · Living Presence`. Decisions opens from the left and System Vitals from the right. Each drawer has a labeled close action and Escape closes either drawer. Mobile drawers respect device safe areas, inset 8px from the usable viewport, own their scrolling, and never introduce horizontal scrolling. Authentication, edge tabs, drawer close actions, and conversation actions retain 44×44 CSS-pixel touch targets.

## Async and resilience

Initial state exposes a status region. Chronicle streaming reports connecting, live, resyncing, authentication-required, and error states. State load failure retains an explicit Retry action. Mutations are pessimistic, suppress duplicate submission, preserve the actionable surface on failure, and refresh canonical server state afterward. Session expiry returns to Creator Access.

## Validation and permissions

Forms declare app-owned validation with `noValidate`; required values and server errors are handled by the owning component. Creator-only actions remain available only in the authenticated workspace. Sensitive values are never echoed into status messages.

## Verification

- Static: `git diff --check`, strict premium UI audit, TypeScript/Vite production build.
- Automated: Vitest and all Playwright suites.
- Browser matrix: Chromium desktop; 1024×768 and 768×1024 tablets; 390×844 and 360×800 phones; 844×390 phone landscape; reduced-motion preference.
- Failure paths: invalid login, unavailable API with Retry, inference unconfigured, rejected/failed decisions.
