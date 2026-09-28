# STF kill switch

The runtime is fail-closed. Global or mission kill state prevents new dispatch. Revocation must be checked again at the privileged boundary before execution. Recovery requires a new authorization transition; never clear a kill switch by replaying stale workflow payloads.

## Operating it

- One Mission: `POST /api/v1/deus/security-missions/{id}/cancel` (reason required). It kills the Mission, revokes its grants and marks it ABORTED; the workflow's abort path also tells the gateway.
- State lives in `kill.json` and `grants.json` under `STF_STATE_DIR` and is re-read on every check. An unreadable file blocks dispatch.
- Recovery is a new contract and a new authorization, never editing the file.
