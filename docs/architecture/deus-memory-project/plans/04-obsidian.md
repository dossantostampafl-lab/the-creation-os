# Exportação Obsidian — plano de implementação

> Para execução futura: usar `superpowers:executing-plans` ou, se escolhido pelo usuário, `superpowers:subagent-driven-development`. Este documento não autoriza iniciar a execução.

**Objetivo:** implementar o subsistemaS4 conforme o contrato auditado.

**Arquitetura:** componentes pequenos no backend existente, migrações aditivas e flags. PostgreSQL é canônico; não introduzir serviços ou APIs pagos.

**Stack:** Python3.12+, FastAPI, SQLAlchemy2, Alembic, PostgreSQL; Redis opcional para aceleração.

**Spec:** [especificação](../specs/04-obsidian.md) e [regras globais](../specs/00-arquitetura.md).

## Restrições globais

Aplicam-se G01–G10 do spec geral. Flags começamfalse; fases opcionais não se tornam dependências. Caminhos abaixo são propostas relativas ao repositório Creation OS, não arquivos deste pacote. `<next>` é nome deliberadamente resolvido consultando `alembic heads` no branch de execução, para não inventar revision sobre uma base que pode avançar.

## Foco de revisão

Ownership antesranking; revogação com indexatrasado; cancellation e limite de recursos; crashes/retries idempotentes; fontesmaliciosas/conflitos. Testes específicos por tarefa abaixo.

## S4T1: Notas e manifest

**Arquivos:** `backend/app/knowledge/obsidian.py`, `backend/app/knowledge/export_manifest.py`, `backend/app/knowledge/export_journal.py`; testes `backend/tests/test_obsidian_export.py`.

**Interface produzida:** async export(scope: Scope, root: Path, cursor: int) -> ExportReport.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_obsidian_export.py` que provem: UUIDpath, títulos../ inocuos; symlinkrecusado; A nãoexportaB; YAMLroundtrip; wikilinksIDs estáveis; repetir não duplica; crash apósreplace/antesmanifest é retomável porprepared/new_hash.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_obsidian_export.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Export snapshot comhash/revisão e journal prepared/applied/confirmed conformeS4, safeYAML, writesatomicfsync/rename; título nunca caminho.

- [ ] Reexecutar `test_obsidian_export.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S4T2: Conflitos, revogação e operação

**Arquivos:** `backend/app/knowledge/export_worker.py`, `backend/app/config.py`, `compose.yml`, `docs/runbooks/deus-knowledge.md`; testes `backend/tests/test_obsidian_lifecycle.py`.

**Interface produzida:** ExportReport(written,removed,skipped,conflicts,cursor); conflito gera relatório e quarentena.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_obsidian_lifecycle.py` que provem: Ediçãousuário não sobrescrita; revogado sai vaultativo comrelatório incluindo conflitos gerados; cleanup_pending retoma após permissionfailure; permissionfailure não falso sucesso; flagoff nãoafetaDEUS.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_obsidian_lifecycle.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Manifest porowner e hashes; implementar política specS4 e volumeprivado; documentar cópiasexternas e edição semimport; comandodeexport explícito semautomação depublicação.

- [ ] Reexecutar `test_obsidian_lifecycle.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## Gate final

Executar testes desta fase e CI geral; obter revisão independente de escopo/autorização e evidências. Testes que dependem de migrações devem usar DBdescartável. Ver matriz A01–A15. Documentar resultados, limitações e flags antes do próximo PR. Não ativar em produção durante a execução local.
