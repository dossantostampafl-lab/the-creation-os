# Contexto compartilhado texto e voz — plano de implementação

> Para execução futura: usar `superpowers:executing-plans` ou, se escolhido pelo usuário, `superpowers:subagent-driven-development`. Este documento não autoriza iniciar a execução.

**Objetivo:** implementar o subsistemaS2 conforme o contrato auditado.

**Arquitetura:** componentes pequenos no backend existente, migrações aditivas e flags. PostgreSQL é canônico; não introduzir serviços ou APIs pagos.

**Stack:** Python3.12+, FastAPI, SQLAlchemy2, Alembic, PostgreSQL; Redis opcional para aceleração.

**Spec:** [especificação](../specs/02-contexto.md) e [regras globais](../specs/00-arquitetura.md).

## Restrições globais

Aplicam-se G01–G10 do spec geral. Flags começamfalse; fases opcionais não se tornam dependências. Caminhos abaixo são propostas relativas ao repositório Creation OS, não arquivos deste pacote. `<next>` é nome deliberadamente resolvido consultando `alembic heads` no branch de execução, para não inventar revision sobre uma base que pode avançar.

## Foco de revisão

Ownership antesranking; revogação com indexatrasado; cancellation e limite de recursos; crashes/retries idempotentes; fontesmaliciosas/conflitos. Testes específicos por tarefa abaixo.

## S2T1: Builder e evidências

**Arquivos:** `backend/app/services/deus_context.py`, `backend/app/services/conversation_context.py`, `backend/app/knowledge/context_trace.py`; testes `backend/tests/test_deus_context.py`.

**Interface produzida:** async build(request: ContextRequest) -> ContextPacket; build_messages(packet: ContextPacket, query: str) -> list[dict[str,str]].

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_deus_context.py` que provem: Fonte externanunca role system; perguntaúltima semduplicação; focoautorizado; timeoutdegrada/cancela query;500 não equivale empty; pacote respeita6trechos/2000tokens/16KiB.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_deus_context.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Usar session_factory/transaçõescurtas, budget300ms e estimativaUTF8/3; proveniência e fatosvivos com horários; preservar identidadeptBR.

- [ ] Reexecutar `test_deus_context.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S2T2: Integração e turnos idempotentes

**Arquivos:** `backend/app/services/deus.py`, `backend/app/voice_session/conversation.py`, `backend/app/schemas/conversation.py`, `frontend/src/api.ts`, `frontend/src/types.ts`, `backend/app/models/conversation_turn.py`, `backend/alembic/versions/<next>_conversation_turn.py`; testes `backend/tests/test_deus_context_channels.py`.

**Interface produzida:** TurnKey(conversation_id, request_id); async ensure_turn(key: TurnKey, content: str) -> TurnRecord; completar resposta unique(turn_id).

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_deus_context_channels.py` que provem: Mesmaquery/foco recebe refs iguais texto/voz; requestretrymesmoconteúdo não duplica; duas requisições pending não iniciam segunda Trinity/inferência; cliente conserva request_id e vozUUIDv5; divergente409; session_id+turn_id distinguem voz; cancelamentos não marcam resultado verified.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_deus_context_channels.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Commit mensagem/turno antes retrieval independente; manter streaming/protocolo voz e Trinitypara planejamento; estado pending/completed/interrupted/failed, CASowner/epoch elease120s/renovação20s conforme specS2; pending409 não duplica geração e completed reutiliza resposta.

- [ ] Reexecutar `test_deus_context_channels.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## S2T3: Cache, rastreabilidade e rollout

**Arquivos:** `backend/app/cache/contracts.py`, `backend/app/cache/routing.py`, `backend/app/config.py`, `backend/app/api/knowledge.py`, `frontend/src/types.ts`, `frontend/src/api.ts`; testes `backend/tests/test_deus_context_rollout.py`.

**Interface produzida:** ContextTraceResponse(id,status,sources,epoch,elapsed_ms); GET /knowledge/context-traces/{id}.

**Consome:** Scope e contratosS1; tarefas posteriores dependem das interfaces definidas nas anteriores. S1T1 define todos tipos de memória; S2T1 define ContextRequest/ContextPacket; S3T1 define Observation/IncidentTransition; S4T1 define ExportReport. Os campos vêm dos specs, sem duplicar definições divergentes.

- [ ] Escrever casos em `test_deus_context_rollout.py` que provem: Flagsfalse reproduzem fluxoatual; fontesBtrace404; knowledgeepoch invalida cache; retrievalligado sempre bypass noMVP; instruçãomemória não habilita capacidade; rollbackpreserva fontes.

- [ ] Rodar, cwdbackend: `../.venv/bin/pytest tests/test_deus_context_rollout.py -q`; confirmar falha antes de implementar. Testes DB exigem PostgreSQL real, semskip contar comoPASS.

- [ ] Implementar: Metadata knowledge_version/retrieval_fingerprint, trace semconteúdoemlogs; frontend fontesopcionais sem quebrarWebSocket; baseline e carga antes ativar.

- [ ] Reexecutar `test_deus_context_rollout.py`; confirmarPASS e executar regressões do subsistema anterior relacionado.

- [ ] Rodar Ruff/mypy nos arquivos; revisar diff, contratos e migration com reviewer; commit próprio para esta entrega.

## Gate final

Executar testes desta fase e CI geral; obter revisão independente de escopo/autorização e evidências. Testes que dependem de migrações devem usar DBdescartável. Ver matriz A01–A15. Documentar resultados, limitações e flags antes do próximo PR. Não ativar em produção durante a execução local.
