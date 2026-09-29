# DEUS Voice: Low-Latency Conversation Design

Date: 2026-09-28
Branch: `feat/deus-voice-latency`

## Objective

Make DEUS conversation feel immediate and continuous in the installed app/PWA while preserving the existing pt-BR behavior. Optimize primarily for perceived latency, reliable capture, and continuity after the wake word `Deus`.

## Confirmed Problems

1. Wake detection currently relies on browser SpeechRecognition.
2. After `Deus`, voice playback can pause listening and create a dead window that clips the user's next words.
3. Browser transcription can remain authoritative when confidence is absent/zero, so poor Chromium transcripts can bypass the higher-quality backend STT.
4. Operational phrases such as `continue`, `corrija`, `verifique`, and similar verbs may enter the full Trinity path, increasing response latency through several inference calls.
5. The current interaction is effectively half-duplex while DEUS is speaking.

## Design

### 1. Wake word stays local/lightweight

The browser/app keeps the existing lightweight wake recognition for `Deus` and supported transcription variants. This avoids streaming all ambient audio continuously to Oracle and keeps activation fast.

Wake detection is only the trigger. It is not the authoritative transcription source once a conversation turn starts.

### 2. No dead window after wake

When `Deus` is detected:

- transition to attentive/conversation state immediately;
- start/keep MediaRecorder capture immediately;
- do not block microphone capture waiting for the spoken acknowledgement;
- acknowledgement must not gate `ears.summon()` or command capture;
- if acknowledgement audio is used, it must be non-blocking from the listening state.

Acceptance case: the user can say `Deus, verifique o projeto` as one natural utterance or say `Deus` followed immediately by the command, without pressing the microphone and without losing the first words.

### 3. Server STT becomes authoritative during active conversation

For an attentive/conversation turn:

- browser SpeechRecognition remains useful for wake detection and provisional UI/interim text;
- capture the actual audio turn;
- on finalized turn, send the audio to the existing backend `/voice/transcribe` flow;
- use the server transcription as the authoritative command when it succeeds;
- fall back to the browser final transcript only when server STT fails or no usable audio is available.

Do not use Chromium confidence as the sole criterion for whether to call server STT. Missing or zero confidence must not cause a bad browser transcript to bypass server transcription.

### 4. Latency-first cognitive fast path

Add a deterministic classifier before the full Trinity path with three categories:

- `conversation`: normal dialogue/question/follow-up; single DEUS inference;
- `simple_action`: low-complexity operational command that does not require multi-agent deliberation; route through a short operational path;
- `mission`: complex, high-impact, ambiguous, multi-step, or governance-sensitive request; use Trinity.

Initial simple-action candidates include short commands such as `continue`, `prossiga`, `mostre`, `verifique`, `repita`, `abra`, `feche`, and bounded corrective follow-ups where the active context already identifies the target.

Commands that create substantial new work, publish/deploy, alter security/governance, spend resources, or otherwise need deliberation remain mission-classified.

The fast path must preserve authorization and safety checks that are independent of Trinity.

### 5. Conversation continuity

Keep the existing conversation ID/history behavior. The change must not reset or fork the active conversation merely because the transport switches from browser transcript to server STT.

### 6. Duplex behavior for this iteration

This implementation removes the wake acknowledgement dead window and restores listening immediately after each DEUS reply. Full acoustic echo-cancelled barge-in while DEUS is already speaking is explicitly deferred unless it can be implemented without destabilizing the current audio stack.

This scope choice favors speed and reliability over a larger streaming/WebRTC rewrite.

## Files Expected to Change

- `frontend/src/voice.ts`
- `frontend/src/CreatorConsole.tsx`
- `frontend/src/voice.test.ts`
- `frontend/e2e/deus-production.spec.ts` or an equivalent focused E2E test
- `backend/app/services/deus.py`
- relevant backend tests for DEUS routing / conversation

`backend/app/services/voice.py` should remain the existing STT provider unless a small compatibility change is required.

## Performance Targets

These are acceptance targets, not guarantees of network/model latency:

- wake-to-capture transition: immediate in the same UI event cycle;
- no intentional TTS wait before command capture;
- simple conversational/simple-action path: at most one primary DEUS generation unless an external operation itself requires more work;
- full Trinity reserved for mission-classified requests;
- STT request performed once per finalized active voice turn, not continuously while idle.

## Tests

### Frontend unit tests

1. `Deus` enters attentive state and capture is ready without waiting for acknowledgement playback to finish.
2. `Deus, <command>` yields the command in the same turn.
3. Active conversation with `confidence === undefined` still attempts server STT.
4. Active conversation with `confidence === 0` still attempts server STT.
5. Successful server STT replaces the provisional browser transcript.
6. Failed server STT falls back to browser transcript.
7. Recognition restart/end does not require a new manual microphone press while the page remains eligible to listen.

### Backend tests

1. ordinary dialogue bypasses Trinity;
2. bounded simple-action follow-up uses the fast path;
3. complex mission verbs still reach Trinity;
4. authorization-sensitive actions cannot bypass required governance;
5. pt-BR system prompt behavior remains unchanged.

### E2E regression

Mock SpeechRecognition + MediaRecorder/STT for:

- wake then immediate command;
- one-utterance `Deus, comando`;
- server STT correction of a poor browser transcript;
- STT fallback failure;
- response followed by automatic re-arming.

## Deployment Validation

After CI is green and the PR is merged:

1. trigger the Oracle deployment/update workflow, not only a check workflow;
2. confirm deployed commit SHA matches merged `main`;
3. smoke-test health, conversation, TTS and STT endpoints;
4. ensure the PWA/service-worker client is not pinned to an older frontend build;
5. perform real-device acceptance on Android with the app in foreground.

## Non-Goals for This Iteration

- guaranteed always-on wake word while Android has suspended/backgrounded the app;
- continuous cloud streaming of ambient audio;
- full WebRTC voice stack rewrite;
- changing the pt-BR behavior that is already working.

## Success Criteria

The change is accepted when, in foreground use, the creator can naturally say `Deus` and continue speaking without touching the microphone; initial words are not lost; the server STT is authoritative for active voice turns; simple commands avoid unnecessary Trinity latency; conversation history remains intact; and all new/affected tests pass.