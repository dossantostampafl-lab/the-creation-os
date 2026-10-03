# S1 — memória canônica, ingestão e recuperação

## Contratos propostos

KnowledgeKind: document, decision, preference, result, diagnostic, derived_note. EpistemicState: recorded, verified, hypothesis. Lifecycle: active, superseded, revoked, deleted. recorded significa que a fonte contém a afirmação, não que ela é verdadeira.

KnowledgeItem(id UUID, creator_id FK, project_id UUID nullable, universe_code nullable, kind, canonical_source_type, canonical_source_id, current_revision_id, deleted_at). KnowledgeRevision(id UUID, item_id FK, ordinal int, content text, content_hash, source_version string, epistemic_state, lifecycle, occurred_at, ingested_at, valid_until nullable, author_type, author_id nullable, derived_from_revision_id nullable). Origem polimórfica resolvida por allowlist de tipos, nunca SQL dinâmico do cliente.

KnowledgeChunk(id, revision_id, ordinal, text, search_vector) com GIN FTS português + termos literais; unique(revision_id,ordinal). KnowledgeRelation(id,creator_id,from_item_id,to_item_id,type,source_revision_id,lifecycle), tipos belongs_to, derives_from, depends_on, supersedes, contradicts, related_to; sem ligações entre proprietários na versão inicial.

KnowledgeOutbox(id UUID,event_type,item_id,revision_id,creator_id,source_version,idempotency_key,created_at); unique(creator_id,idempotency_key). KnowledgeConsumerReceipt(consumer_name,event_id,creator_id,outcome,processed_at), unique(consumer_name,event_id). KnowledgeConsumerCheckpoint(consumer_name,creator_id,last_sequence) apenas como métrica, não como filtro de descoberta. Adicionar sequence BIGINT monotônica à outbox; não usar UUID como ordenação. KnowledgeEpoch(creator_id,version BIGINT) incrementa para criar, corrigir, revogar ou excluir na mesma transação.

ProjectFocus usa ConversationMemory com chave active_project_id, validada contra projeto autorizado; não inventar projeto a partir de palavra isolada. KnowledgeProject(id,creator_id,title,status) agrupa documentos e missões; associação MissionProject explícita. Universo existente é categoria global, não prova de ownership.

## Fonte e autoridade

Scope(creator_id, project_id opcional) vem do actor/token ou serviço interno explicitamente vinculado; ignorar creator_id enviado pelo usuário. Registro de documento manual é fonte tipada local. Message e Mission resolvem proprietário via Conversation/Mission; execução e invocação via missão. UniverseMemory sem dono demonstrável fica fora do backfill até haver associação explícita. Chronicle actor_id isolado não prova proprietário: resolver agregado de domínio. Origem ausente/inacessível vai para relatório de quarentena, nunca owner por heurística.

Decisões explícitas do usuário preservam autoria; resposta do DEUS é recorded/derived_note, não verified. Promover para verified exige evidência de execução/teste ou ato explícito autorizado, sem alterar aprovação de ações. Relação contradiz não resolve conflito automaticamente. Status atual é consultado no domínio na hora de responder.

## Ingestão e invalidação

write_revision(scope,candidate,idempotency_key) resolve fonte sob autorização; valida tamanho/encoding; grava item/revisão/evento/epoch numa transação. Lock de item evita corrida de revisões; constraints unicidade de ordinal/idempotência. Chave repetida com mesmo hash devolve o mesmo resultado; payload diferente com a mesma chave retorna409, sem sobrescrita.

Atualizar item exige expected_revision_id; corrida retorna409. Revogar/excluir incrementa epoch e invalida busca imediatamente pelo JOIN da revisão corrente e do estado canônico, mesmo antes da limpeza assíncrona. Resultado com origem de domínio apagada não é emitido. Cache de retrieval inclui creator, foco, epoch e versão de política. Antes de inserir evidências no contexto, revalidar candidatos da mesma transação/snapshot consistente; para ação, revalidar permissões e estado novamente no executor.

Indexador processa eventos já confirmados da outbox em lotes até100 com SELECT FOR UPDATE SKIP LOCKED e anti-JOIN de receipts do consumer, sem LLM. Não selecionar somente sequence > checkpoint: sequences são atribuídas antes do commit, e commits concorrentes podem chegar fora de ordem. Receipt e índice são gravados na mesma transação; evento não confirmado só ficará elegível quando sua transação concluir. Efeito de indexação e avanço do checkpoint são transacionais; retomada e evento repetido são idempotentes. Índice FTS e chunks pertencem a revisão específica. Erros de um item são registrados como rejeição/quarentena e não travam outros indefinidamente; receipt só é emitido após resultado durável de sucesso ou rejeição. Atualização canônica usa current_revision_id, não o evento mais recente observado; processar evento antigo não reinstala revisão superseded. Retenção da outbox depende de receipts de todos consumidores obrigatórios, nunca apenas MAX(sequence).

Backfill: dry-run produz contagem/hash/ownership/quarentena por fonte. Importação por lotes usa IDs/versões/hash estáveis. Não copiar disco, credenciais ou todo histórico do host. Limite texto por fonte256KiB; chunk8000 caracteres e Unicode normalizadoNFC; documentos maiores são rejeitados413 com orientação de dividir, não truncados silenciosamente.

## Retrieval

retrieve(scope,query,focus,budget) filtra fontes autorizadas/vigentes antes de ranking. Ordem: referência explícita/ID; correspondência literal de título/código; FTS; recência; relações até1 salto. No MVP pesos fixos auditáveis: ID3, literal2, FTS normalizado1, recência até0.2. Deduplicar item/revisão e diversidade de fonte; top6. Query máximo2048 caracteres; parâmetros SQL bound.

Retornar RetrievalResult(status ok|empty|timeout|unavailable, evidences, knowledge_epoch, elapsed_ms, policy_version). empty não é falha técnica. Atraso do índice não impede consulta por ID e revisão corrente. Corpus de testes decide qualidade da busca; sem fonte adequada, responder com limitação em vez de completar como fato.

## API proposta

Sob /api/v1/knowledge: POST /projects; POST /items; GET /items/{id}; POST /items/{id}/revisions; POST /items/{id}/revoke; DELETE /items/{id}; POST /search. Auth soberana existente; retornar404 para item de outro escopo. Corpo sem autoridade/creator_id. GET permite histórico explicitamente solicitado com lifecycle visível; retrieval normal exclui revogados. Paginação cursor com limite25 e máximo100. Imports internos via KnowledgeService, não gateway shell.

Sem upload binário ou fetch arbitrário no MVP: texto manual e fontes internas. Extração PDF/Office/HTTP via MCP exigiria plano próprio de limites/isolamento e validação de origem.

## Contratos fechados após revisão independente

Revisões são imutáveis. Lifecycle muda criando revisão de transição, inclusive tombstone para revoked/deleted; current_revision_id do item é ponteiro canônico mutável. GET histórico mostra transição; retrieval só admite revisão corrente active. Tombstone pode ter conteúdo vazio e referencia revisão anterior; conteúdo antigo não é duplicado para justificar retenção. Remoção física conforme política continua invalidando o item e dependências.

Operação promote_verified(scope,item_id,expected_revision_id,evidence_revision_ids,actor_id) cria revisão com evidências verificáveis e origem da promoção. Introduzir KnowledgeEvidence(revision_id,evidence_revision_id,creator_id) e KnowledgeDependency(derived_revision_id,source_revision_id,creator_id). Uma nota pode depender de várias fontes. IDs/projetos/relações/dependências têm constraints compostas de owner; não aceitar link que cruza proprietários. Relações/dependências cíclicas são rejeitadas na ingestão. Uma dependência revogada/inacessível torna o derivado inelegível, inclusive transitivamente; a busca resolve o fechamento e valida permissões/fontes antes de retornar. Limite de32 dependências e8 níveis; exceder retorna conflito e exige reduzir/reestruturar derivação, não ignorar parte da proveniência.

Idempotency fingerprint usa JSON canônico de todos campos semânticos: fonte/versão, proprietário autorizado, conteúdohash, tipo, estadoepistêmico, lifecycle, referências/evidências/dependências e validade/ocorrência fornecidas. Excluir somente IDs/timestamps gerados pelo servidor e métricas de transporte. Mesmo texto com outra evidência/estado não é mesmo payload;409 se chave reaproveitada. Verified exige evidência em estado verificável do domínio/teste ou promoção explícita registrada pelo Creator; nunca só opinião do modelo.

Admissão de fonte de domínio exige adapter que valide acesso e detecte versão/revogação. Adicionar hooks transacionais para fontes inicialmente suportadas (Message/Conversation/Mission/Task e resultados) registrando invalidation/outbox/epoch nas operações oficiais. Mudança fora do serviço ainda é detectada pelo resolver ao consultar dependências; se não há versionamento verificável, fonte não é eligible para backfill/citação até criar adapter. Não afirmar que qualquer linha legada já possui suporte. S2 inicialmente faz bypass de cache de resposta sempre que retrieval está ligado; reativar cache documental depende de demonstrar invalidation para todas fontes suportadas. Cache de índices não é usado sem revalidar origem e dependências.
