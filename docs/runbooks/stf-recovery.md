# STF recovery

1. Keep privileged dispatch disabled.
2. Verify OPA, NATS JetStream, Temporal and grant-validation health.
3. Verify Chronicle/evidence integrity before resuming.
4. Restart workers; Temporal replay must reconstruct workflow state.
5. Never replay a state-changing action unless its idempotency record proves it did not complete.
6. If sandbox probe is unavailable, privileged execution remains blocked.
