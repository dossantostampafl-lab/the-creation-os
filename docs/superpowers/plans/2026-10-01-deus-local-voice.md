# Local speech implementation and verification

Authorized by the user after selecting the Kokoro pm_santa sample. Execution is
performed in the existing repository; code review is independent.

1. Add failing adapter tests for fragmented text, 400 ms silence, explicit
   commits, wake-question preservation, error propagation and credentials.
2. Implement local adapters against existing gateway interfaces. Share models,
   use independent recognition and cancellable queued synthesis; never call
   paid inference fallback in local mode.
3. Package CPU dependencies and persist downloaded public models in a volume.
   Verify actual synthetic speech before activation and warm before readiness.
4. Run focused voice tests, static checks, complete CI with disposable database,
   frontend tests and browser tests; review and resolve important findings.
5. Validate actual models on the ARM host before switching; then activate local
   voice with readiness rollback and exercise authenticated public speech,
   response audio, typed chat and conversation persistence.

Do not claim human microphone accuracy, perceived naturalness or latency below
one second from synthetic inputs. Record failures and actual timing limits.
