# DEUS Conversation Greenfield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing DEUS voice conversation subsystem with a realtime, Android-first Creator↔DEUS session using ElevenLabs realtime STT/TTS, FreeLLMAPI streaming first, Anthropic fallback, and no microphone button between turns.

**Architecture:** A single authenticated backend Voice Session Gateway owns session state, ElevenLabs STT/TTS streams, inference routing, cancellation and latency telemetry. The browser owns only microphone capture, VAD/barge-in, WebSocket transport and streaming playback. Legacy browser SpeechRecognition/MediaRecorder orchestration is deleted after the new path passes deployed acceptance.

**Tech Stack:** Python 3.12, FastAPI WebSocket, SQLAlchemy async, Redis, httpx/websockets-compatible FastAPI stack, React/TypeScript, Web Audio/AudioWorklet, Vitest, Playwright, GitHub Actions, Oracle Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-30-deus-conversation-greenfield-design.md`

## Global Constraints

- Wake phrase is exactly **Deus**; normal language is **pt-BR**.
- FreeLLMAPI is the primary conversational provider; Anthropic/Claude is fallback.
- ElevenLabs uses the existing API key and voice ID for STT/TTS.
- Realtime STT model is `scribe_v2_realtime`.
- No provider API key reaches the browser.
- No browser-native `SpeechRecognition` in the new production path.
- Normal conversation bypasses SOPHIA, ROKHMAN and Trinity.
- Protected actions remain governed after conversational acknowledgement.
- Android Chrome on the Oracle deployment is a mandatory acceptance gate.
- Legacy voice code is removed in the same delivery after cutover acceptance.

## Review Focus

- Expired/replayed WebSocket ticket must be rejected and never create a usable session.
- Stale audio/model/TTS events from a cancelled turn must never reach the active turn.
- DEUS playback must not retrigger wake detection or become Creator text.
- Network reconnect during a committed turn must not duplicate the persisted Creator message.
- FreeLLM first-token timeout/failure must switch once to Anthropic without interleaving provider text.

---

### Task 1: Voice-session authentication ticket and protocol

**Files:**
- Create: `backend/app/voice_session/__init__.py`
- Create: `backend/app/voice_session/tickets.py`
- Create: `backend/app/voice_session/protocol.py`
- Create: `backend/tests/test_voice_session_protocol.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `issue_voice_ticket(creator_id: str) -> str`, `consume_voice_ticket(ticket: str) -> str`; protocol event models with `session_id`/`turn_id`.
- Consumes: existing `settings.secret_key`, Redis URL and sovereign Creator identity.

- [ ] **Step 1: Write failing tests** for single-use ticket, expiry, malformed ticket, protocol frame validation and stale turn IDs.
- [ ] **Step 2: Run** `cd backend && pytest tests/test_voice_session_protocol.py -q`; Expected: FAIL because package/interfaces do not exist.
- [ ] **Step 3: Implement minimal ticket + protocol code**. Ticket is short-lived, single-use, Redis-backed; no access token appears in WebSocket URL.
- [ ] **Step 4: Run test and full backend suite**; Expected: PASS.
- [ ] **Step 5: Commit** `feat: add secure DEUS voice session protocol`.

### Task 2: Direct streaming DEUS inference with deterministic fallback

**Files:**
- Create: `backend/app/voice_session/inference.py`
- Create: `backend/tests/test_voice_session_inference.py`
- Modify: `backend/app/inference/router.py` only if a generic streaming fallback primitive is required.

**Interfaces:**
- Consumes: existing `InferenceProvider.stream`, registry, conversation message history.
- Produces: `stream_deus_reply(...)->AsyncIterator[VoiceTextDelta]` and provider/fallback metadata.

- [ ] **Step 1: Write failing tests** proving FreeLLM first, Anthropic on timeout/error, no interleaving, no Trinity invocation, and stale-turn cancellation.
- [ ] **Step 2: Run** targeted test; Expected: FAIL for missing adapter.
- [ ] **Step 3: Implement minimal streaming adapter** with 2500 ms first-token deadline and one fallback attempt.
- [ ] **Step 4: Run targeted + full backend suite**; Expected: PASS.
- [ ] **Step 5: Commit** `feat: stream DEUS inference with fallback`.

### Task 3: ElevenLabs realtime STT and TTS adapters

**Files:**
- Create: `backend/app/voice_session/stt.py`
- Create: `backend/app/voice_session/tts.py`
- Create: `backend/tests/test_voice_session_elevenlabs.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `deploy/oracle/set-voice.sh`

**Interfaces:**
- Produces: realtime STT partial/commit events and streaming TTS audio chunks.
- Consumes: existing ElevenLabs key, voice ID, TTS model; STT model `scribe_v2_realtime`.

- [ ] **Step 1: Write failing tests** for endpoint/config payload, Portuguese STT, audio chunk validation, provider timeout, and no secret logging.
- [ ] **Step 2: Run** targeted test; Expected: FAIL for missing adapters.
- [ ] **Step 3: Implement adapters**; provider credentials remain backend-only.
- [ ] **Step 4: Run targeted + full backend suite**; Expected: PASS.
- [ ] **Step 5: Commit** `feat: add ElevenLabs realtime voice adapters`.

### Task 4: Backend Voice Session Gateway

**Files:**
- Create: `backend/app/voice_session/session.py`
- Create: `backend/app/voice_session/metrics.py`
- Create: `backend/app/api/voice_session.py`
- Create: `backend/tests/test_voice_session_gateway.py`
- Modify: `backend/app/api/__init__.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: authenticated ticket endpoint and `/voice/session` WebSocket protocol.

- [ ] **Step 1: Write failing gateway tests** for wake+command same utterance, wake separate command, exactly-once commit, barge-in, reconnect, provider failure and telemetry.
- [ ] **Step 2: Run** targeted test; Expected: FAIL for missing route/session.
- [ ] **Step 3: Implement explicit state machine** `DISCONNECTED→CONNECTING→ARMED→WAKE_DETECTED→LISTENING→COMMITTING→THINKING→SPEAKING→LISTENING`.
- [ ] **Step 4: Run targeted + full backend suite**; Expected: PASS.
- [ ] **Step 5: Commit** `feat: add realtime DEUS voice gateway`.

### Task 5: Frontend realtime voice client

**Files:**
- Create: `frontend/src/voice-session/protocol.ts`
- Create: `frontend/src/voice-session/audio-capture.ts`
- Create: `frontend/src/voice-session/vad.ts`
- Create: `frontend/src/voice-session/player.ts`
- Create: `frontend/src/voice-session/session.ts`
- Create: `frontend/src/voice-session/useDeusVoiceSession.ts`
- Create: `frontend/src/voice-session/session.test.ts`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Consumes: Task 4 ticket + WebSocket protocol.
- Produces: React hook state `ready|listening|thinking|speaking|reconnecting|error`, transcript and response events.

- [ ] **Step 1: Write failing Vitest tests** for state machine, reconnect, stale turn rejection, barge-in/player cancellation and no button between turns.
- [ ] **Step 2: Run** `cd frontend && npm test -- voice-session/session.test.ts`; Expected: FAIL for missing modules.
- [ ] **Step 3: Implement minimal client modules** using one microphone graph and AudioWorklet/Web Audio; no Web Speech API.
- [ ] **Step 4: Run targeted + full frontend tests/build**; Expected: PASS.
- [ ] **Step 5: Commit** `feat: add realtime DEUS browser voice client`.

### Task 6: CreatorConsole cutover and UX

**Files:**
- Modify: `frontend/src/CreatorConsole.tsx`
- Modify: `frontend/src/CreatorConsole.css`
- Create: `frontend/e2e/deus-voice-session.spec.ts`

**Interfaces:**
- Consumes: `useDeusVoiceSession`.
- Produces: visible `Pronto/Ouvindo/Pensando/Falando/Reconectando` states and text timeline updates.

- [ ] **Step 1: Write failing Playwright/Vitest coverage** for wake, five continuous turns, Portuguese response, barge-in, fallback indicator and reconnect.
- [ ] **Step 2: Run tests**; Expected: FAIL while console uses legacy hooks.
- [ ] **Step 3: Cut CreatorConsole to the new hook** while preserving text input and governed proposal UI.
- [ ] **Step 4: Run frontend tests/build/E2E**; Expected: PASS.
- [ ] **Step 5: Commit** `feat: cut DEUS console to realtime voice session`.

### Task 7: Deployment, telemetry and smoke coverage

**Files:**
- Modify: `deploy/oracle/set-voice.sh`
- Modify: `deploy/oracle/smoke-test.sh`
- Modify: `.github/workflows/deploy.yml`
- Create/modify backend tests for configuration and telemetry.

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: Oracle deploy config for realtime STT, voice health proof and smoke evidence.

- [ ] **Step 1: Write failing config/smoke assertions** for `scribe_v2_realtime`, voice-session availability and FreeLLM primary/Anthropic fallback configuration.
- [ ] **Step 2: Run relevant tests/shell validation in CI**; Expected: FAIL before deploy changes.
- [ ] **Step 3: Implement deploy and smoke updates** reusing existing secrets.
- [ ] **Step 4: Run CI-equivalent checks**; Expected: PASS.
- [ ] **Step 5: Commit** `ops: deploy realtime DEUS voice session`.

### Task 8: Remove legacy voice subsystem

**Files:**
- Delete or reduce: `frontend/src/voice.ts`
- Delete/rewrite: `frontend/src/voice.test.ts`
- Delete/rewrite: `frontend/e2e/deus-voice-latency.spec.ts`
- Remove obsolete: `backend/app/api/voice.py`, `backend/app/services/voice.py`, `backend/app/schemas/voice.py`, `backend/tests/test_voice.py` only where no longer referenced.
- Modify imports and package references repository-wide.

**Interfaces:**
- Consumes: all new voice-session interfaces.
- Produces: no production dependency on browser SpeechRecognition or legacy short-clip transcription.

- [ ] **Step 1: Add failing repository guard test** asserting production frontend has no `SpeechRecognition` dependency and old endpoints are unreferenced.
- [ ] **Step 2: Run guard;** Expected: FAIL while legacy remains.
- [ ] **Step 3: Delete legacy code and dead compatibility branches**; keep rollback only in Git history.
- [ ] **Step 4: Run backend/frontend/full E2E/build/security suites**; Expected: PASS.
- [ ] **Step 5: Commit** `refactor: remove legacy DEUS voice stack`.

### Task 9: Whole-branch review, CI, merge, Oracle deployment and real acceptance

**Files:** no feature code unless review findings require a TDD fix.

**Interfaces:** validates the complete system.

- [ ] **Step 1: Run full CI and security workflows**; zero blocking failures.
- [ ] **Step 2: Perform whole-branch code review** against spec and Review Focus; Critical/Important findings get one RED→GREEN fix pass.
- [ ] **Step 3: Merge only after required checks are green.**
- [ ] **Step 4: Run GitHub Actions Deploy `update`, then `set-inference-freellmapi`, `set-voice`, and `smoke-test` on Oracle using existing secrets.**
- [ ] **Step 5: Execute the real Android acceptance sequence:** "Deus", prompt without button, complete pt-BR transcript, five follow-ups, barge-in, controlled FreeLLM fallback, latency/provider telemetry.
- [ ] **Step 6: Only declare Ready when deployed Android acceptance and legacy-removal verification are both green.**

## Self-review

- Spec coverage: wake, continuous listening, pt-BR, realtime STT/TTS, FreeLLM primary, Anthropic fallback, direct DEUS path, barge-in, observability, Android, deployment and legacy removal are each mapped to tasks.
- Type consistency: session/turn identifiers originate in Task 1 and are consumed unchanged by Tasks 2-6.
- Review Focus: all five listed failure modes are explicitly tested by their owning tasks.
- Proportion: plan specifies interfaces, tests and gates; implementation bodies remain with the executor.
