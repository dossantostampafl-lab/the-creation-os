# DEUS Voice Low-Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make foreground DEUS voice conversation immediate and continuous: no dead window after `Deus`, server STT authoritative for active turns, and simple commands avoiding unnecessary Trinity inference.

**Architecture:** Keep browser SpeechRecognition as a lightweight wake/interim layer. Once attentive, record one utterance, prefer the existing backend `/voice/transcribe` result, and fail open to browser text. In the backend, replace the coarse execution-verb gate with a deterministic route classifier that preserves Trinity for substantial or governance-sensitive work while allowing bounded contextual actions to remain single-pass.

**Tech Stack:** React 19, TypeScript 7, Vite/Vitest, Playwright, FastAPI/Python 3.12, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-deus-voice-latency-design.md`

## Global Constraints

- Preserve the existing pt-BR system prompt and voice language behavior.
- Do not continuously stream ambient audio to Oracle; STT runs once per finalized attentive turn.
- Wake detection remains local/lightweight for this iteration.
- Full acoustic echo-cancelled barge-in while DEUS is speaking is out of scope.
- Browser transcript is the fail-open fallback when server STT is unavailable, empty, blocked by cooldown, or has no usable captured audio.
- Commands that publish/deploy, change security/governance, spend resources, authorize/cancel missions, or create substantial new work must not bypass governance.
- No new runtime dependency is required for this iteration.

## Review Focus

- Microphone permission denied or MediaRecorder unavailable: conversation must fall back to browser text without crashing or permanently disabling wake recognition.
- Backend STT timeout/error/empty text: exactly one active-turn attempt, then browser text is submitted.
- `Deus, <comando>` in one utterance and bare `Deus` followed immediately by a command: no duplicate command and no clipped first word.
- Short sensitive-looking commands such as `deploy agora`, `publique`, `autoriza`, and `cancela a missão` must remain governed even if they are syntactically short.
- A reply finishing TTS must re-arm the existing conversation; wake acknowledgement itself must never be the gate that re-opens capture.

---

### Task 1: Make active-turn audio authoritative and remove the wake dead window

**Files:**
- Modify: `frontend/src/voice.ts`
- Modify: `frontend/src/CreatorConsole.tsx`
- Test: `frontend/src/voice.test.ts`
- Test: `frontend/e2e/deus-production.spec.ts`

**Interfaces:**
- Consumes: existing `transcribeVoice(audio: Blob, signal?: AbortSignal): Promise<VoiceTranscript>` from `frontend/src/api.ts`.
- Produces: `useDeusEars` behavior where attentive turns attempt server STT whenever usable captured audio exists, independent of Chromium confidence; browser final text remains fallback.
- Produces: wake handling where `onWake` enters conversation/listening immediately and any `Estou aqui.` acknowledgement is non-blocking with respect to capture.

- [ ] **Step 1: Add failing unit coverage for transcript-selection policy**

In `frontend/src/voice.test.ts`, add tests around an exported pure helper `preferServerTranscript(browserText: string, serverText: string | null | undefined): string` asserting:
- non-empty trimmed server text wins;
- empty/whitespace/null server text falls back to browser text.

Run: `cd frontend && npm test -- voice.test.ts`
Expected: FAIL because `preferServerTranscript` does not exist.

- [ ] **Step 2: Implement the pure transcript selector**

In `frontend/src/voice.ts`, export `preferServerTranscript(browserText: string, serverText: string | null | undefined): string` and use it from the attentive-turn transcription path.

Run: `cd frontend && npm test -- voice.test.ts`
Expected: PASS for the new selector tests and existing wake/decision tests.

- [ ] **Step 3: Add failing E2E coverage for authoritative server STT with undefined/zero browser confidence**

In `frontend/e2e/deus-production.spec.ts`, extend the existing fake SpeechRecognition setup with a fake `MediaRecorder`/`getUserMedia` and route `**/api/v1/voice/transcribe`. Add two cases where the browser emits an incorrect transcript with confidence `undefined` and `0`, the server returns `verifique o projeto`, and the request to `/conversations/.../deus` must contain `verifique o projeto`.

Run: `cd frontend && npm run test:e2e -- --grep "server STT"`
Expected: FAIL because current code bypasses STT when confidence is absent and only invokes it on explicitly low confidence.

- [ ] **Step 4: Make server STT authoritative for every finalized attentive turn with usable audio**

In `frontend/src/voice.ts`, change the current `maybeImproveTranscript(browserText, averageConfidence)` flow so Chromium confidence no longer decides whether STT is attempted. `finishCapture()` runs once; if the blob is usable and STT cooldown is not active, call `transcribeVoice(audio)` and return `preferServerTranscript(browserText, improved.text)`. On STT error, set the existing retry/cooldown state and return `browserText`. If no usable audio exists, return `browserText` immediately.

Keep the existing fail-open semantics and do not start capture while idle/sleeping merely to improve wake detection.

Run: `cd frontend && npm run test:e2e -- --grep "server STT"`
Expected: PASS.

- [ ] **Step 5: Add failing E2E coverage for wake followed immediately by speech**

Change the existing wake-acknowledgement E2E scenario so after the fake recognizer emits bare `Deus`, it emits `verifique o projeto` before acknowledgement playback can finish. Assert the command reaches DEUS without a manual mic action. Add a same-utterance case `Deus, verifique o projeto` and assert only one command is submitted.

Run: `cd frontend && npm run test:e2e -- --grep "wake"`
Expected: FAIL because `CreatorConsole` currently waits for `voice.speak(...).onEnd` before calling `ears.summon()` and `paused` includes `voice.speaking`.

- [ ] **Step 6: Remove acknowledgement as a listening gate**

In `frontend/src/CreatorConsole.tsx`:
- on `onWake`, call `setConversing(true)` and `ears.summon()` immediately;
- do not wait for ElevenLabs acknowledgement completion before summoning ears;
- use a non-gating acknowledgement path only if it does not set the ears into a paused state. If the current `voice.acknowledge()` still sets `voice.speaking`, omit the spoken wake acknowledgement rather than sacrifice capture latency for this iteration;
- keep `paused: !enabled || pending || voice.speaking` for normal DEUS replies, because full barge-in while DEUS speaks is explicitly out of scope.

Run: `cd frontend && npm run test:e2e -- --grep "wake"`
Expected: PASS with immediate command capture and no duplicate submission.

- [ ] **Step 7: Run the complete frontend unit/build gate**

Run: `cd frontend && npm run build && npm test`
Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add frontend/src/voice.ts frontend/src/CreatorConsole.tsx frontend/src/voice.test.ts frontend/e2e/deus-production.spec.ts
git commit -m "fix: make DEUS voice capture continuous and STT authoritative"
```

---

### Task 2: Add a deterministic latency-first DEUS route classifier

**Files:**
- Modify: `backend/app/services/deus.py`
- Test: `backend/tests/test_deus_conversation.py`

**Interfaces:**
- Produces: `classify_deus_route(content: str) -> Literal["conversation", "simple_action", "mission"]`.
- `needs_trinity(content: str) -> bool` remains available for compatibility but becomes `classify_deus_route(content) == "mission"`.
- `DeusConversationService._reason(...)` continues to call Trinity only when `needs_trinity` is true; authorization/safety checks outside Trinity remain untouched.

- [ ] **Step 1: Add failing classifier tests**

In `backend/tests/test_deus_conversation.py`, add a parametrized test proving:
- `conversation`: `Qual é o status disso?`, `e agora?`, `como ficou o que falamos?`;
- `simple_action`: `continue`, `prossiga`, `mostre`, `verifique`, `repita`, `abra`, `feche`, `corrija esse erro` when the wording is bounded/contextual;
- `mission`: `implemente um novo sistema`, `crie um universo`, `publique em produção`, `deploy agora`, `altere a governança`, `configure segurança`, `automatize pagamentos`, `autoriza`, `cancela a missão`.

Also assert `needs_trinity(...)` is true only for the mission set.

Run: `cd backend && pytest tests/test_deus_conversation.py -q`
Expected: FAIL because `classify_deus_route` does not exist and the current `_ACTION_REQUEST` routes bounded corrections/continuations through Trinity.

- [ ] **Step 2: Implement the deterministic classifier**

In `backend/app/services/deus.py`:
- define a `DeusRoute = Literal[...]` alias;
- define explicit regexes for governance/sensitive mission verbs and substantial creation/execution verbs;
- define a conservative simple-action pattern limited to short contextual commands (`continue/prossiga/mostre/verifique/repita/abra/feche`) plus bounded corrective follow-ups such as `corrija isso/esse erro` without a new project/objective clause;
- implement `classify_deus_route(content)` with precedence `mission` > `conversation` > `simple_action` > conservative `mission` for ambiguous non-dialogue statements;
- implement `needs_trinity(content)` as a wrapper around the classifier.

The classifier must remain deterministic and zero-model-call.

Run: `cd backend && pytest tests/test_deus_conversation.py -q`
Expected: PASS.

- [ ] **Step 3: Add failing inference-count coverage for simple actions**

Add an async test with a real `TrinityEngine` + stub router, call `DeusConversationService.respond(...)` with `continue` and `corrija esse erro`, and assert the router receives only one `route == "deus"` request and no `trinity:sophia` or `trinity:rockmam` request.

Run: `cd backend && pytest tests/test_deus_conversation.py -q`
Expected: FAIL until the classifier is wired through `needs_trinity`.

- [ ] **Step 4: Verify mission requests still traverse Trinity**

Add/retain an async test using `implemente um novo sistema` or an equivalent mission phrase and assert at least a Trinity route is attempted before DEUS final generation. Sensitive authorization/mission-decision flows remain handled by existing proposal/mission APIs and must not be collapsed into the simple path.

Run: `cd backend && pytest tests/test_deus_conversation.py -q`
Expected: PASS after classifier implementation.

- [ ] **Step 5: Run backend quality gates**

Run: `cd backend && ruff check app tests && mypy app && pytest`
Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/services/deus.py backend/tests/test_deus_conversation.py
git commit -m "perf: fast-path bounded DEUS commands"
```

---

### Task 3: Prove the complete voice turn and regression behavior

**Files:**
- Modify: `frontend/e2e/deus-production.spec.ts`
- Modify only if required by failing regression: `frontend/src/voice.ts`, `frontend/src/CreatorConsole.tsx`, `backend/app/services/deus.py`

**Interfaces:**
- Consumes Task 1 authoritative active-turn STT and immediate wake capture.
- Consumes Task 2 deterministic route classification.
- Produces an end-to-end regression contract for wake -> STT -> DEUS -> spoken reply -> automatic re-arm.

- [ ] **Step 1: Add the complete foreground conversation E2E**

In `frontend/e2e/deus-production.spec.ts`, mock recognition, MediaRecorder, `/voice/transcribe`, `/conversations/.../deus`, and voice synthesis for this sequence:
1. emit `Deus`;
2. emit poor browser text while server STT returns `verifique o projeto`;
3. assert exactly one DEUS request contains the server transcript;
4. finish mocked DEUS TTS;
5. emit a follow-up without saying `Deus` again;
6. assert the follow-up is accepted in the same conversation;
7. assert no manual microphone action occurred.

Run: `cd frontend && npm run test:e2e -- --grep "continuous DEUS voice"`
Expected: PASS once Tasks 1 and 2 are complete; if it fails, debug the smallest violated interface rather than weakening the assertions.

- [ ] **Step 2: Run the full frontend gate**

Run: `cd frontend && npm run build && npm test && npm run test:e2e`
Expected: PASS.

- [ ] **Step 3: Run the full backend gate**

Run: `cd backend && ruff check app tests && mypy app && pytest`
Expected: PASS.

- [ ] **Step 4: Run the repository CI-equivalent smoke gate**

Use the existing `.github/workflows/ci.yml` via a pull request. Required green jobs: backend, frontend, stack, and runtime-build/release job(s) emitted by CI.

Expected: every required CI job PASS.

- [ ] **Step 5: Commit Task 3 if E2E changes were added after Task 1**

```bash
git add frontend/e2e/deus-production.spec.ts
git commit -m "test: cover continuous DEUS voice turn"
```

---

### Task 4: Merge-safe production validation on Oracle

**Files:**
- No product-code changes expected.
- Operational workflow: `.github/workflows/deploy.yml`.

**Interfaces:**
- Consumes a green PR containing Tasks 1-3.
- Produces evidence that Oracle is serving the merged commit rather than a stale frontend/backend build.

- [ ] **Step 1: Open PR from `feat/deus-voice-latency` to `main` and require CI green**

Expected: PR reports all CI checks successful before merge.

- [ ] **Step 2: Merge only after the green gate**

Expected: merged `main` commit SHA is recorded.

- [ ] **Step 3: Trigger the Oracle deployment workflow with its update/deploy action, not check-only mode**

Expected: workflow completes successfully and reports the deployed revision.

- [ ] **Step 4: Verify deployed revision and service health**

Confirm the Oracle deployment uses the merged `main` SHA and smoke-test API readiness, frontend health, DEUS conversation, TTS, and STT endpoints.

Expected: all health/smoke checks PASS.

- [ ] **Step 5: Validate PWA freshness and real-device acceptance**

Ensure the service worker is not holding an older frontend. On Android with the app foregrounded, verify: say `Deus` and continue naturally, initial words are not lost, no mic press is required, a follow-up works after DEUS replies, and simple commands return without the former Trinity delay.

Expected: foreground acceptance PASS. Background/locked-screen always-on wake remains explicitly out of scope.
