# Diagnóstico independente — plano de implementação

> Para execução futura: usar `superpowers:executing-plans` ou, se escolhido pelo usuário, `superpowers:subagent-driven-development`. Este documento não autoriza iniciar a execução.

**Objetivo:** implementar o subsistemaS3 conforme o contrato auditado.

**Arquitetura:** componentes pequenos no backend existente, migrações aditivas e flags. PostgreSQL é canônico; não introduzir serviços ou APIs pagos.

**Stack:** Python3.12+, FastAPI, SQLAlchemy2, Alembic, PostgreSQL; Redis opcional para aceleração.

**Spec:** [especificação](../specs/03-diagnostico.md) e [regras globais](../specs/00-arquitetura.md).

## Restrições globais

Aplicam-se G01–G10 do spec geral. Flags começamfalse; fases opcionais não se tornam dependências. Caminhos abaixo são propostas relativas ao repositório Creation OS, não arquivos deste pacote. `<next>` é nome deliberadamente resolvido consultando `alembic heads` no branch de execução, para não inventar revision sobre uma base que pode avançar.

## Foco de revisão

Ownership antesranking; revogação com indexatrasado; cancellation e limite de recursos; crashes/retries idempotentes; fontesmaliciosas/conflitos. Testes específicos por tarefa abaixo.

## S3T1: Observações e regras

**Arquivos:** `backend/app/diagnostics/contracts.py`, `backend/app/diagnostics/rules.py`, `backend/app/diagnostics/probes.py`; testes `backend/tests/test_diagnostics_rules.py`.

**Interface produzida:** async collect(now: datetime) -> list[Observation]; evaluate(observations: list[Observation], previous: IncidentState) -> list[IncidentTransition].

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_diagnostics_rules.py` que provem: 3falhasabre;2sucessosrecupera; validade45s; running semprogresso só suspeita sobregra; inferência semdados=unknown.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_diagnostics_rules.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Coletores bounded2s e interval15s; relógioinjetável/testes semsleep; semshell/docker.sock nem fornecedorremoto periódico.

- [ ] Reexecutar `test_diagnostics_rules.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S3T2: Journal, replay e volume

**Arquivos:** `backend/app/diagnostics/journal.py`, `backend/app/diagnostics/worker.py`, `compose.yml`, `backend/app/config.py`; testes `backend/tests/test_diagnostics_journal.py`.

**Interface produzida:** append(observation: Observation) -> int; async replay(scope: Scope, limit: int = 100) -> ReplayReport.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_diagnostics_journal.py` que provem: DBdownpreserva journal; replayduplicado idempotente; observedat antigo permanece stale;100MiBfullexplicitamentealerta; reinício retoma.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_diagnostics_journal.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: SQLiteprivado/fsync e volume100MiB lógico; apagar sóobservações confirmadas após7dias; reserva para marcador spoolfull; processo independente e backoff.

- [ ] Reexecutar `test_diagnostics_journal.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S3T3: Incidentes, heartbeats e integração

**Arquivos:** `backend/app/diagnostics/service.py`, `backend/app/knowledge/provenance.py`, `backend/app/services/deus_context.py`, `backend/app/models/diagnostics.py`, `backend/app/worker.py`; testes `backend/tests/test_diagnostics_integration.py`.

**Interface produzida:** async publish(scope: Scope, observation: Observation) -> Incident | None; async heartbeat(worker_id: str, boot_id: str, observed_at: datetime) -> None.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_diagnostics_integration.py` que provem: Outroowner não recebeincidentes; soberanoausente localonly; workerstopdiagnóstico continua; Redisdownnão perdeepisódio; recoverednota supersede antiga.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_diagnostics_integration.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Registrar fontes tipadas de diagnóstico; schemaaditivo; heartbeat nãoaltera reconciler. Entregar fatosvalidos e histórico aoContextBuilder, semautocorreção.

- [ ] Reexecutar `test_diagnostics_integration.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## Gate final

Executar testes desta fase e CI geral; obter revisão independente de escopo/autorização e evidências. Testes que dependem de migrações devem usar DBdescartável. Ver matriz A01–A15. Documentar resultados, limitações e flags antes do próximo PR. Não ativar em produção durante a execução local.
