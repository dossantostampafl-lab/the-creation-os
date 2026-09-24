# Cyber Range v1 — Recovery Inventory

Date: 2026-09-24
Branch: `feat/cyber-range-v1-recovery`
Recovery base: `feat/phase9-task1-reconciliation`

## Purpose

Recover the previously delivered Creation Cyber Range v1 without treating conversation memory as implementation evidence and without inventing unverified historical paths.

## Verified preserved evidence

The preserved README identifies the package root as `cyber-range-v1/` and confirms these v1 components:

- OWASP Juice Shop target, localhost only.
- OWASP WebGoat/WebWolf target, localhost only.
- Range Controller API.
- Mission catalog.
- Evidence journal.
- Qualification rubric.
- PowerShell `start` / `stop` / `reset` / `verify` scripts.

Verified exposed endpoints from the preserved package documentation:

- Controller API: `http://127.0.0.1:7070/docs`
- Juice Shop: `http://127.0.0.1:3000`
- WebGoat: `http://127.0.0.1:8080/WebGoat`

Verified safety boundary:

- Published services bind to `127.0.0.1`.
- Both Docker networks are `internal: true`.
- Production networks and real credentials are excluded.
- Security Onion is deliberately not bundled in v1.
- CALDERA is deliberately deferred beyond the base v1 package.

## Repository findings

- Historical branch name exists: `feat/cyber-range-v1-codespaces`.
- Its current HEAD is the same code baseline as `main` (`dafc1edebf01b0ff583175fe91087ad2272fc0f2`).
- The current tree at that HEAD contains no `cyber-range-v1/` package.
- No current separate Cyber Range implementation is therefore recoverable from that branch head.
- The canonical project branch preserves the Cyber Range design, amendment and implementation-plan documents.

## Historical artifact gap

The available preserved evidence does **not** prove the exact original internal filenames for:

- Range Controller source modules;
- mission catalog files;
- evidence journal implementation files;
- qualification rubric implementation files;
- `scripts/stop.ps1` contents;
- the original archive byte contents for `cyber-range-v1.zip` or `cyber-range-v1.1-codespaces.zip`.

These paths must not be represented as historically recovered unless a later artifact proves them.

## Recovery ruling

`Ruling: restore behavior and safety contracts under the verified package root, while distinguishing reconstructed files from historically recovered files — because the package contract is preserved but several internal historical filenames are not — cost if wrong: reconstructed internals may differ from the old zip while preserving its externally documented behavior.`

## Recovery target

The restored package must remain a local, explicitly authorized training/verification environment and must not grant or imply authority over real systems. It must stay subordinate to the canonical Security Task Force authorization and evidence model.

## Next implementation gate

1. Re-read the canonical Cyber Range design and implementation plan.
2. Define tests for the verified v1 safety and service contracts before implementation.
3. Reconstruct `cyber-range-v1/` from those tests and preserved evidence.
4. Verify loopback binding, internal networks, service health, reset behavior and evidence persistence.
5. Record reconstructed-vs-recovered provenance for every restored file.
