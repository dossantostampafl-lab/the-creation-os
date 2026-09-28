# Execution ledger — docs/superpowers/plans/2026-09-28-deus-voice-latency.md

- Approved execution method: native / inline execution in the current session.
- Base branch: `main`.
- Working branch: `feat/deus-voice-latency`.
- TDD RED tests committed before production changes.
- Pre-flight: Task 1 produces authoritative active-turn STT and immediate post-wake listening; Task 3 consumes those behaviors. Task 2 produces the fast-path routing contract independently.
- RED evidence: `96b7cce2` backend Trinity routing regression; `33b7fa52` frontend STT/dead-window regressions. CI confirmed the intended failures before production changes.
- Product fix: `64f964c0` makes captured attentive-turn audio authoritative for server STT, re-arms the ears immediately after `Deus`, and keeps the premium wake acknowledgement outside the blocking `voice.speaking` state.
- Backend fast path: bounded contextual commands (`continue`, `prossiga`, `mostre`, `verifique`, `repita`, `abra`, `feche`, bounded corrections) remain single-pass; substantial, deployment, security/governance, authorization and cancellation requests remain governed by Trinity.
- Service-level proof: `7433cd92` asserts bounded commands issue only the `deus` inference route with a real `TrinityEngine` present.
- Voice E2E proof: `d19b0f6d` covers high and zero Chromium confidence, server-STT authority, bare wake followed immediately by speech, and one-breath `Deus, <comando>` without duplicate submission.
- Security hardening: `827c076f` replaces the user-facing simple-action regex with an exact normalized lookup after CodeQL reported `py/polynomial-redos`; targeted backend tests, Ruff and mypy passed.
- Legacy E2E alignment: `c8ae9db4` updates older browser-speech assertions to the approved non-blocking premium acknowledgement contract; the complete frontend build, unit suite and Playwright suite passed in the applying workflow before commit.
- Final gate trigger: this ledger commit is intentionally user-authored so CI and Security run on the consolidated head rather than being suppressed as workflow-generated events.
