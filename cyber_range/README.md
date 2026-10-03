# Creation Cyber Range v1

Isolated local environment for training, experimentation, replay and verification. The Range never grants production authority.

## Included baseline

- Range Controller API on `127.0.0.1:7070`
- OWASP Juice Shop on `127.0.0.1:3000`
- OWASP WebGoat on `127.0.0.1:18080`
- OWASP WebWolf on `127.0.0.1:9090`
- declared scenario catalog
- append-style evidence files in the `range_evidence` Docker volume, read with
  `docker compose -f cyber_range/compose.yml cp controller:/evidence ./evidence-export`
- disposable scenario state
- SaveRange snapshot/restore lifecycle for controller state
- start/stop/reset/verify lifecycle scripts

## Safety boundary

The vulnerable Juice Shop and WebGoat containers now have exactly one interface: the Docker `range_targets` network, declared `internal: true`. They publish no host ports and never join `range_loopback` or `range_control`. Host loopback access is provided by small non-root, read-only, capability-dropped TCP proxies that have fixed targets in Compose; those proxies have no Docker socket, writable volume, arbitrary destination parameter, or production credential. The controller is separate from the vulnerable-target network and exposes only its declared lifecycle API on loopback.

The publication bridge still has IP masquerading disabled, and the Range must never be attached to production networks or given production credentials/data. The fixed proxies materially reduce target-to-host/routed reachability, but this project still treats the Range as disposable training infrastructure rather than as production authority. Any future component that can execute commands or arbitrary network actions must remain behind the strong-isolation gateway and its fail-closed policy.

## Windows / Docker Desktop

```powershell
.\\cyber_range\\scripts\\start.ps1
.\\cyber_range\\scripts\\verify.ps1
.\\cyber_range\\scripts\\reset.ps1
.\\cyber_range\\scripts\\stop.ps1
```

The qualification baseline is stored at `cyber_range/qualification/rubric.json`. SH levels are evidence-based; the presence of the rubric does not itself grant certification.

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

Evidence in the `range_evidence` volume is intentionally preserved by controller reset; Docker state
is disposable. It lives in a volume rather than a bind mount because the controller runs as a
non-root user, which cannot write into a directory the host owns.


## SaveRange

The controller can preserve and restore the declared Cyber Range controller state without exporting targets, credentials, or host data.

- `POST /snapshots` creates an immutable JSON snapshot of declared scenario state and appends an audit-evidence record.
- `GET /snapshots` lists saved snapshots.
- `POST /snapshots/{snapshot_id}/restore` restores only catalog-declared scenario state and appends an audit-evidence record.
- `GET /state` returns the current controller state.

Snapshots live in the dedicated `range_snapshots` Docker volume. `POST /reset` clears disposable state but intentionally preserves both evidence and snapshots.


### Hospedagem separada de produção

Os alvos vulneráveis não possuem mais interface na rede de publicação do host: ficam somente em `range_targets`, que é interna. Os proxies de loopback são de destino fixo, sem privilégios, sem volumes e sem Docker socket. Mesmo assim, o Range continua sendo infraestrutura descartável de treinamento: não anexe redes, dados ou credenciais de produção. O relay autentica controles e os proxies reduzem a superfície de publicação, mas nenhum deles concede autoridade sobre ambientes `real:*`.
