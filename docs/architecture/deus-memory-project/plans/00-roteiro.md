# Roteiro completo, separado por entregas

Status:draft auditável; implementação não iniciada. Base50924e3. Specs em ../specs/. Arquivos da implementação futura estarão em branch própria, não neste pacote.

| Ordem | Plano | Dependência | Entrega revisável |
|---|---|---|---|
| 1 | [S1 memória](01-memoria.md) | Nenhuma nova | Fontes/revisões, API, ingestão/backfill, FTS |
| 2 | [S2 contexto](02-contexto.md) | S1 | DEUS lembra entre conversas no texto/voz |
| 3 | [S3 diagnóstico](03-diagnostico.md) | S1; integração exigeS2 | Observador independente e incidentes |
| 4 | [S4 Obsidian](04-obsidian.md) | S1 | Vault exportável, sem dualwrite |

S3/S4 podem ser preparados independentemente quandoS1 estiver estável; S2 é prioridade funcional. Nenhuma fase exige embeddings ou MCPs adicionais.

## Sequência de PRs

PR1 schema/constraints/proveniência; PR2 indexação/backfill/retrieval; PR3 ContextBuilder e testes; PR4 turnos/paridadevoz/cache/trace; PR5 diagnósticoregras/journal; PR6 incidentes/heartbeats; PR7 Obsidian. Números são sequência lógica, não númerosGitHub reservados. Cada PR usa a base vigente, migrations sem múltiplosheads e CI.

## Auditoria antes de executar

Revisar specs e matriz; aprovar escopo memória/contexto; confirmar exportação unidirecional e diagnóstico observador. Medir baseline do host. Garantir backup/restaurável antes de futuras migrations. Só então escolher execução: nativa ou subagentes por tarefa, com reviewer independente. Nenhuma seleção de execução foi feita neste pacote.

## Testes e rollout

Seguir ../audit/02-aceitacao.md. Começar com corpusfixture e projeto piloto. Flagsfalse porpadrão; ativar ingestão, validarbackfill/quarentena, depoisretrieval para piloto; diagnóstico/export são flagsdistintas. Realizar medição sobcarga antes ampliar. Isolamento/injection/duplicação são gatesbloqueadores.

Rollback: desligar flagafetada, restaurar caminho anterior; manter fonte/eventos. Não fazer downgrade destrutivo de produção para desligar comportamento. Projeções reconstruíveis, FTS continua semembedding.

## Extensões deliberadamente sem plano de execução agora

Embedding local: escolher modelo/dimensão/recursos somente por benchmark. Obsidian bidirecional: merge/importação e conflitos próprios. Autocorreção: leases/fencing/idempotência deefeitos e política de autorização. Multitenancy integral dolegado: revisar APIsglobais, cursores/eventos e RLSse pertinente. Estes assuntos têm viabilidade condicional, não fazemparte doMVP aprovado automaticamente.
