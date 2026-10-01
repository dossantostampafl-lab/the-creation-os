# Local voice only cleanup implementation plan

**Goal:** Remove retired paid speech integration while preserving local voice, wake word, interruption, history and typed chat.

**Architecture:** Keep the existing authenticated voice-session gateway, Kokoro pm_santa synthesis, Vosk recognition and FreeLLMAPI. Remove alternate speech adapters, paid voice configuration and deployment path. Fresh installations leave voice disabled until model preparation succeeds.

**Requested scope:** User requests full tests and removal of the old chat integration.

## Tasks

- [x] Add regression checks that runtime, deployment and current operator guides contain only local speech; run to establish failures.
- [x] Remove retired adapter tests and migrate gateway tests to local adapter factories. Preserve synthesis-error, recognition-failure, cancellation and authentication tests.
- [x] Remove alternate voice settings, adapters, provider fallback, quota UI and paid deployment command. Keep disabled-by-default startup before model installation.
- [x] Rewrite current operator guides and remove obsolete speech design documents. Keep one implementation specification for the current local voice.
- [ ] Run backend checks, frontend checks and full CI. Request independent code review and fix findings.
- [ ] Merge verified change, sanitize obsolete voice environment values on production without logging secrets, deploy and validate public voice plus typed chat in desktop and phone viewports.

## Review focus

- Fresh install without speech assets must boot with voice disabled.
- Enabled local voice must warm models before readiness.
- Local synthesis failures must produce a safe error rather than mislabelled recognition failures.
- Existing history and barge-in cancellation must retain behavior.
- Deployment secret transport and model cache must remain intact.
