# Security Task Force — local start/stop

Start the control plane:

```powershell
docker compose --profile security-task-force up -d --build
```

The profile contains Temporal, NATS/JetStream, OPA, the STF worker and the Rust gateway. The gateway has no host-published port and no Docker socket. Cyber Range remains a separate profile.

Stop:

```powershell
docker compose --profile security-task-force down
```
