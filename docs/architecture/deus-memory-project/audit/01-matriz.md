# Auditoria de viabilidade e limites

Status: auditoria arquitetural documental. Não houve benchmark, invasão, implementação ou validação de implantação destas propostas.

| Decisão | Classificação | Condição/evidência | Gate |
|---|---|---|---|
| PostgreSQL existente como base | Pode | Infraestrutura/modelos já existem; migração aditiva | S1 testes com PostgreSQL real |
| FTS e relações SQL | Pode | Não exige nova API/modelo | Corpus pt-BR e consulta GIN parametrizada |
| Memória transversal aos Universos | Pode com condição | Universo é global; dono precisa vir da fonte | Rejeitar/backfill quarentena sem ownership |
| Mesmo contexto texto/voz | Pode com condição | Rotas atuais diferem | Paridade, streaming, cancelamento e p95 |
| Busca vetorial local | Condicionado | Nenhum adapter local implementado; CPU/RAM desconhecidos | Benchmark de recall/latência antes de escolher modelo |
| Obsidian export unidirecional | Pode | Markdown é projeção, sem segundo mestre | Paths, conflito, revogação, manifest |
| Obsidian bidirecional | Adiado | Precisa política de merge e import | Projeto separado |
| Diagnóstico independente | Pode com condição | Hoje probes são on-demand e worker acopla refresher | QuedaDB/Redis, journal, heartbeat |
| Autocorreção de produção | ForaMVP | Diagnóstico não confere permissão | Política de ação/reversão e autorização separadas |
| Neo4j/Qdrant/broker adicional | Desnecessário agora | Não há necessidade medida | Reconsiderar somente com benchmark |
| Corpus inteiro no prompt | Rejeitado | Limite/latência/conflito | Retrieval limitado porbudget |
| Memória como role system | Rejeitado | helper atual promove system_notes | Conteúdo externo fora de system e policy de execução |
| Memória como autorização | Rejeitado | Memória atual já veta autoridade | Executor consulta autorização canônica |
| Todos26 MCPs ativos | Rejeitado | Pacotes não são integração | Seleção porcapacidade; nenhum necessário paraM1 |
| Fake embeddings semânticos | Rejeitado | primeiros8 caracteres não medem significado | FTS noMVP; modelo real posterior |
| Novo projeto multitenant completo | ForaMVP | auth atual é Creator soberano | Novo knowledge estritamente scoped; não alegar isolamento global pronto |

## Registro de riscos

R01 stale por atrasoindexer: joins revisãocorrente+origem+epoch síncrono; gate revogar durante indexer parado.
R02 ownership ausente UniverseMemory: não atribuir dono pelo primeiroCreator; gate quarentena.
R03 injection: conteúdo fonte nunca system; domínio bloqueia ações independentemente do texto; gate estrutural+executor.
R04 sobrecarga CPU/DB: deadline/statement_timeout/budgets; medir p95 concorrente; embeddings adiados.
R05 eventos duplicados/ordem: idempotency hash, sequenceBIGINT,checkpoint transacional, teste crash antes/depoiscommit.
R06 novas fontes alteram cache: epoch/fingerprint/ACL, status bypass; gate revisão/erasure.
R07 transação longa texto: persistir turno antesinferência; request_id para não duplicar retries; não reutilizar AsyncSession concorrente.
R08 vozinterrompida: cancelarrotaquery, tracecanceled, resultadoincompleto não verified.
R09 falhaDB ouhost: journalbounded apenas diagnóstico; semhostobservadorexterno nãohácobertura.
R10 arquivoObsidianeditado: hashmanifest/conflict/quarentena; nãoautorizar silenciosamenteimport.
R11 flagsligadasantesmigrar: startup valida schema; readiness indicaerrocontrolado, rollbackflag.
R12 lixo sensível: sanitizar conteúdo ingestível; credenciais fora/logs semconteúdo; testar fixtures sintéticas.

## Bloqueadores antes do rollout

Ownership e proveniência implementados; fontes revogadas não voltam poríndice/cache; nenhuma memória liberaação; commit/turnretrycompatíveis; prazo/cancelamento reais; revisão schema/fixtures; PostgreSQL real e CI.

## Ressalvas da base atual

Chronicle possui lockglobal: usar para mudanças duráveis, não para amostras altafrequência. APIs system globais são soberanas; novos endpoints scoped não corrigem automaticamente todo legado. Reconciler startup semlease/fencing requer plano próprio antes deautocorreção/múltiplosworkers concorrentes. Não ampliar M1 com reescrita desses subsistemas.
