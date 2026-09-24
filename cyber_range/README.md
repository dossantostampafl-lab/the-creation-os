# Creation Cyber Range v1 — Canonical Recovery

This directory is the canonical reconstruction of the previously delivered local Cyber Range foundation.

## Provenance

The historical package was documented under `cyber-range-v1/`. Repository reconciliation proved that its current historical branch no longer contains a separate implementation. The Phase 9 canonical plan assigns the recovered implementation to `cyber_range/`. Files in this directory are therefore reconstructed from verified package behavior and canonical design constraints unless explicitly marked otherwise.

## Included baseline

- Range Controller API on `127.0.0.1:7070`
- OWASP Juice Shop on `127.0.0.1:3000`
- OWASP WebGoat on `127.0.0.1:8080`
- OWASP WebWolf on `127.0.0.1:9090`
- declared scenario catalog
- append-style evidence files under `./evidence`
- disposable scenario state
- SaveRange snapshot/restore lifecycle for controller state
- start/stop/reset/verify lifecycle scripts

## Safety boundary

All published ports bind to loopback. Range Docker networks are internal. The controller has no arbitrary shell or external-target execution API. Production networks and real credentials must never be attached to this compose project.

## Start

```bash
./cyber_range/scripts/start.sh
```

## Verify

```bash
./cyber_range/scripts/verify.sh
```

## Reset disposable state

```bash
./cyber_range/scripts/reset.sh
```

Evidence under `cyber_range/evidence/` is intentionally preserved by controller reset; Docker state is disposable.


## SaveRange

The controller can preserve and restore the declared Cyber Range controller state without exporting targets, credentials, or host data.

- `POST /snapshots` creates an immutable JSON snapshot of declared scenario state and appends an audit-evidence record.
- `GET /snapshots` lists saved snapshots.
- `POST /snapshots/{snapshot_id}/restore` restores only catalog-declared scenario state and appends an audit-evidence record.
- `GET /state` returns the current controller state.

Snapshots live in the dedicated `range_snapshots` Docker volume. `POST /reset` clears disposable state but intentionally preserves both evidence and snapshots.
