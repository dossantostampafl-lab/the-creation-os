# DEUS Conversation Greenfield Design

**Date:** 2026-09-30  
**Status:** Proposed for Creator review  
**Scope:** Complete replacement of the existing DEUS browser voice conversation subsystem.  
**Execution:** No implementation begins until this spec is approved and an implementation plan is written.

## 1. Intent

Rebuild the Creator ↔ DEUS conversation path from zero as a dedicated real-time voice subsystem. The existing wake-word, browser SpeechRecognition and voice-turn orchestration are not implementation references and will be retired after the new subsystem passes real acceptance tests.

The target experience is conversational rather than command-driven:

1. The Creator opens the interface and grants microphone permission once.
2. The interface remains ready without requiring the microphone button for each turn.
3. The Creator says **"Deus"**.
4. DEUS acknowledges immediately in the configured ElevenLabs voice.
5. The Creator speaks naturally in Portuguese.
6. DEUS transcribes the full utterance, reasons directly, begins answering as soon as the first model text is available, and speaks the response progressively.
7. When DEUS finishes, the system returns to listening automatically.
8. The Creator can interrupt DEUS by speaking; playback stops and the new turn begins.

Ordinary conversation must never traverse SOPHIA, ROKHMAN or Trinity. Governed execution remains a separate path for actions that can change code, infrastructure, security posture, money, credentials, permissions, production state or other protected resources.

## 2. Non-negotiable requirements

- Wake phrase: **Deus**.
- Language: **pt-BR** throughout STT, prompting, response text and TTS.
- Primary inference provider: **FreeLLMAPI**.
- Fallback inference provider: **Klaus**. Klaus is the Creator-specified logical fallback. Its concrete provider/model/API mapping must be verified from an explicit project configuration before deployment; it must not be silently substituted with Anthropic/Claude.
- Voice provider: **ElevenLabs** using the existing API key and existing configured voice ID.
- Reuse existing secrets; do not expose provider API keys to the browser.
- No browser-native `SpeechRecognition` dependency in the new conversation path.
- No requirement to press the microphone button between turns.
- No SOPHIA, ROKHMAN or Trinity inference before a normal DEUS answer.
- Streaming model response and streaming ElevenLabs TTS are required for the normal conversation path.
- Android Chrome is a first-class acceptance platform, not a mocked afterthought.
- CI success alone is not proof of completion; a real deployed Android session must pass the acceptance sequence.

## 3. Council review

The architecture was reviewed from five independent engineering perspectives:

### 3.1 Real-time voice engineer

Recommendation: keep a single microphone session alive while the page is active, capture audio through Web Audio / AudioWorklet, and send normalized mono PCM frames to one authenticated backend WebSocket. Do not alternate competing browser recognition and MediaRecorder pipelines.

### 3.2 Backend/distributed-systems engineer

Recommendation: make one backend **Voice Session Gateway** own the session state, provider connections, cancellation, turn IDs and ordering. Every audio, transcript, model and TTS event must carry the same session and turn identifiers so stale events cannot overwrite a newer turn.

### 3.3 LLM/inference engineer

Recommendation: use the existing streaming provider interfaces. Normal conversation explicitly requests `freellmapi` first and the configured `klaus` fallback second. The fallback begins only when the primary raises a timeout, authentication/rate-limit/unavailable error, or fails the configured first-token deadline. Provider choice must be observable per turn.

### 3.4 Android/web engineer

Recommendation: avoid Web Speech API behavior differences. Keep microphone permission and the audio graph stable for the whole active session. Use browser-side VAD only for local speech/activity detection and barge-in; authoritative text comes from the server STT stream.

### 3.5 Reliability/security engineer

Recommendation: provider keys remain server-side, raw audio is not persisted by default, pre-wake audio is discarded, logs contain IDs/latencies/statuses rather than raw credentials or full audio. Every external stream must have cancellation, timeout and reconnect behavior.

Council consensus: build a new isolated real-time session pipeline rather than continue modifying the existing `frontend/src/voice.ts` behavior.

## 4. Architecture

### 4.1 Components

#### A. Frontend Voice Client

New focused modules, independent of the old voice implementation:

- `voice-session/audio-capture.ts` — microphone acquisition and AudioWorklet lifecycle.
- `voice-session/vad.ts` — local speech activity and barge-in signal.
- `voice-session/protocol.ts` — typed WebSocket message contracts.
- `voice-session/player.ts` — queued streaming audio playback and immediate cancellation.
- `voice-session/session.ts` — explicit state machine and reconnect policy.
- `voice-session/useDeusVoiceSession.ts` — React integration only.

The frontend performs no LLM routing and stores no provider secret.

#### B. Backend Voice Session Gateway

New backend package:

- `app/voice_session/protocol.py`
- `app/voice_session/session.py`
- `app/voice_session/stt.py`
- `app/voice_session/inference.py`
- `app/voice_session/tts.py`
- `app/voice_session/metrics.py`
- `app/api/voice_session.py`

The gateway owns one WebSocket per authenticated Creator session and orchestrates the full turn.

#### C. ElevenLabs realtime STT

Use the existing `ELEVENLABS_API_KEY` and switch the realtime conversation path to `scribe_v2_realtime`.

The backend opens the ElevenLabs realtime STT WebSocket and forwards PCM audio frames. Partial transcripts are used for wake detection and UI feedback. Committed transcripts are authoritative for LLM input.

Existing `ELEVENLABS_STT_MODEL_ID=scribe_v2` is not sufficient for the realtime path and must be migrated for this subsystem to `scribe_v2_realtime`.

#### D. Direct DEUS inference stream

For every ordinary conversational turn:

- preferred provider: `freellmapi`
- fallback provider: `klaus` (logical name; concrete adapter mapping must be verified before deployment)
- streaming required
- health preflight skipped on the interactive critical path
- short bounded context loaded directly from the conversation store
- no Trinity preprocessing

FreeLLMAPI already exposes streaming in the current inference layer. Klaus must be bound through the same streaming-provider interface once its concrete adapter mapping is verified; no other provider is to be substituted by assumption.

#### E. ElevenLabs realtime TTS

Use the existing:

- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_MODEL_ID`

Normal default remains `eleven_flash_v2_5` unless real latency/quality tests prove another configured model is preferable.

The backend streams model text chunks into ElevenLabs TTS WebSocket and forwards returned audio chunks immediately to the browser.

### 4.2 Wake acknowledgement

To make the wake interaction feel immediate, the authenticated frontend preloads one short acknowledgement generated with the configured ElevenLabs voice, e.g. **"Estou aqui."**

The audio is generated/cached server-side using ElevenLabs and contains no browser speech synthesis fallback. When the backend confirms the wake phrase, the frontend can play this already-buffered ElevenLabs clip immediately while the same microphone session remains open.

The acknowledgement is not counted as a user turn and does not invoke an LLM.

## 5. Session state machine

Authoritative states:

```
DISCONNECTED
  -> CONNECTING
  -> ARMED
  -> WAKE_DETECTED
  -> LISTENING
  -> COMMITTING
  -> THINKING
  -> SPEAKING
  -> LISTENING
```

Additional transitions:

- any active state -> `RECOVERING` on recoverable transport/provider failure
- `RECOVERING -> ARMED` after reconnect
- `SPEAKING -> LISTENING` on barge-in
- any active state -> `DISCONNECTED` on logout, explicit stop, tab teardown or unrecoverable authentication failure

A monotonically increasing `turn_id` is created when a committed user utterance enters the DEUS inference path. Audio and text belonging to an older `turn_id` are ignored after cancellation.

## 6. Wake phrase and listening behavior

### 6.1 Armed state

The microphone is active while the DEUS surface is active and permission is granted. Browser-side VAD suppresses transport of long silence where practical, but the backend remains the authority.

### 6.2 Wake detection

Wake detection uses normalized partial STT. Accepted canonical phrase is `deus`; recognition normalization may tolerate obvious transcription variants only if tests prove low false-positive risk.

Before wake detection:

- no LLM request
- no conversation message persisted
- raw audio is not stored

After wake detection:

- backend emits `wake.detected`
- frontend plays cached ElevenLabs acknowledgement
- state becomes `LISTENING`
- transcript following the wake word can become the same turn, so "Deus, como está o projeto?" does not require a second utterance

### 6.3 End of user turn

Use STT committed transcript / VAD commit semantics rather than arbitrary browser timers. The backend sends the committed utterance into inference exactly once.

## 7. Barge-in and echo handling

When DEUS is speaking:

- microphone capture stays alive
- browser echo cancellation remains enabled
- local VAD detects a new human speech onset
- frontend immediately stops queued DEUS audio
- frontend sends `barge_in` for the active turn
- backend cancels remaining TTS and model streaming for that turn where possible
- a new listening turn begins

The system must never treat the DEUS TTS playback as a new Creator command. Tests must include speaker playback into an active microphone simulation and real Android verification.

## 8. Inference policy

### 8.1 Ordinary conversation

Normal dialogue goes directly to DEUS.

It may use:

- recent conversation messages
- compact persisted memory/context
- current authenticated Creator/session identifiers

It must not invoke SOPHIA, ROKHMAN or Trinity before answering.

### 8.2 Governed actions

If the conversational model identifies a capability/action intent involving protected effects, the spoken/text response still remains conversational. Execution becomes a separate governed intent submitted to the existing authorization path.

Examples that remain governed:

- deploy or publication
- modifying source code
- production changes
- security policy changes
- credentials and secrets
- payments or money movement
- database migrations
- permission changes

This separation prevents governance latency from blocking normal dialogue while preserving authority boundaries.

## 9. Provider fallback policy

For the conversational stream:

1. Start FreeLLMAPI.
2. If it produces a valid first token within the configured interactive deadline, keep that provider for the turn.
3. If it fails with timeout, rate limit, authentication failure, unavailable/circuit-open state, malformed stream, or misses the first-token deadline, cancel it and start Klaus.
4. Never interleave text from two providers in one turn.
5. Record `provider_selected`, `fallback_reason` and latencies.
6. If both providers fail, DEUS speaks a short deterministic service message using ElevenLabs; it does not hang silently.

Recommended initial first-token deadline: **2.5 seconds** for FreeLLM in the interactive path. This is a tuning parameter validated against deployed measurements, not a permanent magic number.

## 10. Latency budget and telemetry

Per turn, record monotonic timestamps for:

- microphone frame received
- first STT partial
- wake detected
- transcript committed
- LLM request started
- first model token
- first TTS text submitted
- first audio chunk from ElevenLabs
- first audio chunk played in browser
- final response completed

Initial acceptance targets on a stable connection:

- wake detected from speech onset: p95 <= 800 ms
- committed transcript to first model token: p95 <= 2.5 s on healthy FreeLLM
- first model token to first playable TTS audio: p95 <= 900 ms
- no hidden multi-second acknowledgement timer
- conversation returns to listening automatically after playback

These are product SLO targets, not unit-test sleeps.

## 11. Security and privacy

- Provider API keys never enter frontend bundles, localStorage, IndexedDB or browser logs.
- Authenticate the voice WebSocket with the existing Creator authentication mechanism.
- Authorize the session to the same Creator identity used by conversation persistence.
- No raw microphone audio persisted by default.
- No full provider credential or Authorization header in logs.
- Rate-limit session creation and reconnect storms.
- Bound frame size, sample rate, session lifetime and transcript size.
- Reject unauthenticated WebSocket upgrades.
- Sanitize telemetry so it can diagnose latency without exposing secrets.
- Existing keys are reused from the Oracle runtime; deployment must not request new credentials when valid ones already exist.

## 12. Error recovery

### STT disconnect

Attempt bounded reconnect. While reconnecting, UI shows an explicit degraded listening state. Do not silently pretend to listen.

### FreeLLM failure

Fail over once to Klaus according to the provider policy.

### TTS disconnect

Reconnect TTS for the active turn once. If speech cannot resume, keep the text response visible and report the voice channel failure.

### Browser audio failure

If microphone permission is revoked or the audio graph fails, show a direct actionable state and require a user gesture only when the browser platform itself requires it.

### Backend WebSocket loss

Reconnect with exponential backoff capped to a short interactive window. A new connection receives a new session transport ID while preserving conversation identity.

## 13. Persistence

Persist only committed semantic events:

- Creator committed utterance
- DEUS final response text
- provider used
- final turn status
- timestamps needed for audit/latency

Do not persist interim STT fragments or raw audio by default.

## 14. Frontend UX contract

The DEUS surface must expose understandable states:

- **Pronto** — armed and waiting for "Deus"
- **Ouvindo** — wake detected / Creator speaking
- **Pensando** — committed transcript sent to inference
- **Falando** — ElevenLabs audio playing
- **Reconectando** — recoverable transport failure
- explicit microphone/provider failure when unrecoverable

The UI must not require the Creator to understand STT/TTS/provider terminology.

## 15. Testing strategy

### Unit

Frontend:
- state transitions
- frame normalization
- wake-event handling
- stale turn rejection
- barge-in cancellation
- player queue/cancel behavior
- reconnect state

Backend:
- protocol validation
- wake normalization
- transcript commit exactly once
- provider primary/fallback selection
- first-token timeout
- stale turn rejection
- cancellation propagation
- credential non-exposure
- persistence rules

### Contract/integration

- fake realtime STT server emitting partial + committed transcripts
- fake streaming FreeLLM server
- forced FreeLLM timeout -> Klaus stream
- fake ElevenLabs TTS chunks
- reconnect and out-of-order event tests
- authentication failure
- duplicate audio frames / duplicate commit protection

### Browser E2E

Playwright proves protocol/state behavior without relying on browser SpeechRecognition.

Required flows:

1. wake + command in one utterance
2. wake then separate command
3. continuous second turn without microphone button
4. barge-in
5. FreeLLM fallback
6. TTS stream playback
7. reconnect without duplicate turn
8. Portuguese-only response contract

### Real deployed acceptance

Mandatory on Android Chrome against the Oracle deployment:

1. Open DEUS.
2. Grant microphone once.
3. Say "Deus".
4. Hear the ElevenLabs acknowledgement promptly.
5. Ask a normal question without touching the microphone button.
6. Verify the complete Portuguese utterance is captured.
7. Hear DEUS begin answering without SOPHIA/ROKHMAN/Trinity delay.
8. Ask at least five consecutive follow-up turns.
9. Interrupt one spoken answer and verify barge-in.
10. Force/observe a controlled FreeLLM failure and verify Klaus fallback.
11. Confirm telemetry identifies the provider and latency stages without exposing credentials.

No release is accepted if this sequence fails even when CI is green.

## 16. Migration strategy

The new subsystem is built alongside the old one behind a dedicated feature switch.

Sequence:

1. Implement new backend Voice Session Gateway.
2. Implement new frontend Voice Client.
3. Add automated unit/contract/E2E coverage.
4. Deploy with old flow still available only for rollback.
5. Pass real Android acceptance.
6. Make new subsystem the default.
7. Remove old browser SpeechRecognition/MediaRecorder orchestration and its tests.
8. Remove obsolete compatibility endpoints only after final regression pass.

No old voice implementation code is copied into the new modules.

## 17. Configuration

Reuse existing runtime configuration wherever valid:

- `FREELLMAPI_API_KEY`
- `FREELLMAPI_MODEL`
- `FREELLMAPI_BASE_URL`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_MODEL_ID`

New or adjusted voice-session settings:

- `ELEVENLABS_STT_MODEL_ID=scribe_v2_realtime`
- `DEUS_VOICE_PRIMARY_PROVIDER=freellmapi`
- `DEUS_VOICE_FALLBACK_PROVIDER=klaus`
- `DEUS_VOICE_FIRST_TOKEN_TIMEOUT_MS=2500`
- `DEUS_VOICE_SESSION_ENABLED=true|false`

Existing secrets remain in the Oracle runtime and must not be copied into repository files.

## 18. Definition of done

The work is complete only when all conditions are true:

- new code path does not use browser SpeechRecognition
- old voice orchestration is no longer the production path
- wake word "Deus" works on deployed Android Chrome
- no microphone button is needed between normal turns
- FreeLLM is observed as primary provider
- Klaus fallback is proven under controlled FreeLLM failure using its explicitly verified adapter/configuration
- ElevenLabs existing voice is used for acknowledgement and all DEUS speech
- normal dialogue bypasses SOPHIA/ROKHMAN/Trinity
- barge-in works
- five-turn continuous conversation works
- telemetry shows latency stages and provider choice
- unit, backend, frontend, integration, E2E, CI and security checks pass
- real Oracle smoke/acceptance passes
- code review finds no unresolved blocking issues
- old broken voice subsystem is removed after the new path is accepted

## 19. Official provider references

- ElevenLabs realtime STT: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
- ElevenLabs server-side realtime STT: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/server-side-streaming
- ElevenLabs realtime TTS WebSocket: https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/realtime-tts
