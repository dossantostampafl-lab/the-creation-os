# DEUS local voice integration

The user selected the unmodified Kokoro `pm_santa` sample and authorized tests
and implementation on 2026-10-01. Replace paid speech inference for the existing
voice-session flow with local Kokoro synthesis and Portuguese Vosk FalaBrasil
recognition. Reuse the existing FreeLLMAPI streaming response, conversation
history, wake word “Deus”, ticket authentication, interruption handling and
PCM protocol. Do not purchase credits or invoke paid model fallbacks.

Use process-shared CPU models in the existing API, lazy imported for installations
that use another voice engine. Warm recognition and acknowledgement before local
API readiness. Keep CPU inference off the event loop and use one synthesis thread and independent recognition on the two-core host. Discard
cancelled synthesis jobs before native computation; an already running native call
finishes without delivering obsolete audio.
Buffer model tokens into phrases for synthesis, producing mono PCM16 at 24 kHz.
Recognize browser PCM16 at 16 kHz; emit changing partials and committed phrases
after 400 ms of quiet, native endpoints, explicit commit or a 30-second cap.
Wake detection remains in the existing gateway, preserving text on either side
of “Deus”. Accuracy and real-microphone latency must not be claimed from synthetic
tests alone.

Models live in a persistent named volume. An explicit setup task downloads and
validates them before switching the environment and restarting the API. Existing
ElevenLabs adapters remain selectable for rollback; duplicated dialogue flows
are not added. In local mode provider failures produce the existing unavailable
response without paid fallback. Validate adapters, actual model audio, full CI,
ARM performance and authenticated public browser behavior before reporting the
production voice as working.
