# Memória e recuperação — plano de implementação

> Para execução futura: usar `superpowers:executing-plans` ou, se escolhido pelo usuário, `superpowers:subagent-driven-development`. Este documento não autoriza iniciar a execução.

**Objetivo:** implementar o subsistemaS1 conforme o contrato auditado.

**Arquitetura:** componentes pequenos no backend existente, migrações aditivas e flags. PostgreSQL é canônico; não introduzir serviços ou APIs pagos.

**Stack:** Python3.12+, FastAPI, SQLAlchemy2, Alembic, PostgreSQL; Redis opcional para aceleração.

**Spec:** [especificação](../specs/01-memoria.md) e [regras globais](../specs/00-arquitetura.md).

## Restrições globais

Aplicam-se G01–G10 do spec geral. Flags começamfalse; fases opcionais não se tornam dependências. Caminhos abaixo são propostas relativas ao repositório Creation OS, não arquivos deste pacote. `<next>` é nome deliberadamente resolvido consultando `alembic heads` no branch de execução, para não inventar revision sobre uma base que pode avançar.

## Foco de revisão

Ownership antesranking; revogação com indexatrasado; cancellation e limite de recursos; crashes/retries idempotentes; fontesmaliciosas/conflitos. Testes específicos por tarefa abaixo.

## S1T1: Modelo e migração aditiva

**Arquivos:** `backend/app/knowledge/contracts.py`, `backend/app/models/knowledge.py`, `backend/alembic/versions/<next>_knowledge.py`; testes `backend/tests/test_knowledge_schema.py`.

**Interface produzida:** KnowledgeCandidate, Scope, KnowledgeRevision, KnowledgeDependency, KnowledgeEvidence, RetrievalResult; modelos conforme specS1.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_knowledge_schema.py` que provem: Unicidade ordinal/idempotency, FKs, sequênciaBIGINT; revisão válida não muda apósgravada. Migração sobe em PostgreSQLreal sem alterar memórias legadas.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_knowledge_schema.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Criar modelos/tabelas e constraints, FTSGIN português e lookup literal; escolher revisionID após conferir Alembicheads.

- [ ] Reexecutar `test_knowledge_schema.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S1T2: Escrita e proveniência

**Arquivos:** `backend/app/knowledge/service.py`, `backend/app/knowledge/provenance.py`, `backend/app/knowledge/repository.py`, `backend/app/api/knowledge.py`, `backend/app/api/__init__.py`; testes `backend/tests/test_knowledge_provenance.py`.

**Interface produzida:** async write_revision(scope: Scope, candidate: KnowledgeCandidate, idempotency_key: str, expected_revision_id: str | None) -> KnowledgeRevision.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_knowledge_provenance.py` que provem: A não lê/grava fonteB; idempotência mesmohash reutilizaID, outrohash409; expectedrevision divergente409; transição cria revisão/tombstone; verified exige evidências; fingerprint inclui estado/refs; UniverseMemory semowner vaiquarentena.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_knowledge_provenance.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Resolver proprietário pororigem allowlist; implementar promote_verified e hooks/adapter de versão para fontes suportadas conforme adendoS1; transação curta item/revisão/outbox/epoch; endpoints autenticados e erros conforme spec.

- [ ] Reexecutar `test_knowledge_provenance.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S1T3: Indexador e backfill

**Arquivos:** `backend/app/knowledge/indexer.py`, `backend/app/knowledge/worker.py`, `backend/app/knowledge/backfill.py`, `backend/app/config.py`, `compose.yml`; testes `backend/tests/test_knowledge_indexer.py`.

**Interface produzida:** async process_batch(consumer: str, limit: int = 100) -> BatchResult; async backfill(scope: Scope, dry_run: bool) -> BackfillReport.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_knowledge_indexer.py` que provem: Crash antescommit não cria receipt; apóscommit/retry não duplica; commitforaordem não perdeevento; eventoantigo não reinstala revisão velha; origemapagada não retorna; não fazembedding/LLM remoto; dryrun não grava.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_knowledge_indexer.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Consumidor independente com SKIPLOCKED/receipts conformeS1, chunkNFC até8000chars; backfill com relatório deowners/quarentena e versionamento determinístico. Flag defaultfalse.

- [ ] Reexecutar `test_knowledge_indexer.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S1T4: Recuperação textual e relações

**Arquivos:** `backend/app/knowledge/retrieval.py`, `backend/app/knowledge/relations.py`; testes `backend/tests/test_knowledge_retrieval.py`.

**Interface produzida:** async retrieve(scope: Scope, query: str, focus: str | None, budget: RetrievalBudget) -> RetrievalResult.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_knowledge_retrieval.py` que provem: Top6 autorizado,1salto; revisão revogada excluída com indexerparado; pontuação determinística; dependência revogada transitiva e owner de relações/projetos validados; nomes técnicos e português; empty distinto deunavailable.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_knowledge_retrieval.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: FTS/literal/ID, pesos do specS1, statementtimeout200ms e revalidação canônica; implementar relações e cache por epoch sem liberar ações.

- [ ] Reexecutar `test_knowledge_retrieval.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## Gate final

Executar testes desta fase e CI geral; obter revisão independente de escopo/autorização e evidências. Testes que dependem de migrações devem usar DBdescartável. Ver matriz A01–A15. Documentar resultados, limitações e flags antes do próximo PR. Não ativar em produção durante a execução local.
