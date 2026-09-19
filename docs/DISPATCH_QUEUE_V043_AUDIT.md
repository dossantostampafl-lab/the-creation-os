# Dispatch Queue v0.4.3 Audit

The Dispatch Queue is a persistent coordination foundation, not an execution
runtime. Enqueue accepts only an authorized Mission's `ready` Task whose persisted
dependencies are `completed`. Agent resolution delegates to Capability Engine.

States are `queued`, `leased`, `acknowledged`, `retry_scheduled`, `failed`,
`dead_lettered`, and `cancelled`. Terminal items cannot be leased or cancelled.

Lease acquisition uses PostgreSQL `FOR UPDATE SKIP LOCKED`, ordered by priority
descending, then availability, creation time, and UUID. Each acquisition creates
a high-entropy opaque token; only its SHA-256 hash is stored. Worker and token must
match for renew, acknowledge, failure, and release.

Failures increment attempts atomically. Retry delay is `base * 2^(attempt-1)` with
a maximum cap. Reaching `max_attempts` moves the item to dead-letter. Tests use no
sleeps.

Endpoints:

- `POST /api/v1/dispatch`
- `GET /api/v1/dispatch`
- `GET /api/v1/dispatch/{id}`
- `POST /api/v1/dispatch/lease`
- `POST /api/v1/dispatch/{id}/renew`
- `POST /api/v1/dispatch/{id}/acknowledge`
- `POST /api/v1/dispatch/{id}/fail`
- `POST /api/v1/dispatch/{id}/release`
- `POST /api/v1/dispatch/{id}/cancel`
- `GET /api/v1/dispatch/{id}/attempts`

The Dispatch Queue does not authorize Missions.
The Dispatch Queue does not execute agents in v0.4.3.
The Dispatch Queue does not manifest results.
Retries do not create authority.

## Stabilization status

| Requirement | Evidence | Result | Test file | Residual risk |
|---|---|---|---|---|
| State machine and backoff | permitted/forbidden transitions and bounds | passed | `test_dispatch_state_machine.py` | none known |
| HTTP and security | all ten endpoints, 401/403/409/422, mass assignment | passed | `test_dispatch_integration.py` | worker authentication remains Creator-mediated |
| PostgreSQL leasing | SKIP LOCKED, distinct items, active-item uniqueness | passed | `test_dispatch_integration.py` | no long-running worker exists |
| Retry/dead-letter | deterministic backoff and terminal limit | passed | `test_dispatch_integration.py`, `test_dispatch_service.py` | administrative requeue is out of scope |
| Capability resolution | existing matcher reused, no Registry mutation | passed | `test_dispatch_integration.py` | requires ready Task and live eligible Agent |
| Migration | 0005→0006→0005→0006 | passed | isolated PostgreSQL | none known |

Implemented: yes. Tested: yes. Stabilized: yes. Applied to main database: yes,
with zero DispatchItems and zero DispatchAttempts after migration.

No agent was executed. No agent runtime was invoked. No Mission was created.
No Mission was authorized. No Task was executed. No manifestation occurred.
Retries did not create authority.
