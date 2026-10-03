# S2 — contexto único para DEUS texto e voz

## Contrato

ContextRequest(creator_id,conversation_id,turn_id,query,channel text|voice,correlation_id). DeusContextBuilder.build(request) -> ContextPacket. ContextPacket(history,live_facts,evidences,retrieval_status,knowledge_epoch,retrieval_fingerprint,focus,trace_id). Trace é metadado auditável; não vira mensagem system com dados externos.

O builder usa session_factory e transações curtas de leitura, nunca uma AsyncSession compartilhada por queries concorrentes. Persistência do turno é concluída antes de abrir recuperação independente; isso requer ajustar transação longa de services/deus.py. Plano mantém estados de turno e resposta sem prometer que falha de inferência volta a apagar pergunta já enviada. Idempotência do turno: request_id UUID recebido ou criado; unique(conversation_id,request_id). Retry reutiliza mensagem de usuário e não duplica resposta. Voz associa session_id + turn_id; turn_id sozinho não é global. TurnRecord contém state pending|completed|interrupted|failed, content_hash, generation_owner UUID, generation_epoch e lease_until. Aquisição é CAS transacional; apenas o owner/epoch vigente pode completar. Pending concorrente retorna409 turn_in_progress com Retry-After, sem segunda geração. Completed devolve resposta existente. Falha/interrupção não é retomada automaticamente como ação: pedido de repetição explícito inicia novo request_id; o registro original continua auditável. Para morte de processo, lease vencida marca failed; não reexecuta efeitos automaticamente. Lease default120s, renovação20s enquanto geração válida; takeover nunca executa ação. O prazo de inferência permanece o do provedor e é medido separadamente do prazo de contexto.

## Construção de mensagens

System: identidade e regras confiáveis, inclusive como interpretar evidência/degradação. Histórico recente: até20 mensagens mantidas com seus papéis. Evidências: bloco delimitado de conteúdo no papel user com indicação explícita de que é material recuperado, antes da pergunta atual; não role system. Snapshot estruturado de fatos internos pode acompanhar bloco, com fonte/observed_at. Pergunta atual continua por último sem duplicar seu registro do histórico.

Essa representação evita promoção estrutural para system, mas não elimina injection por si só. Tools não são liberadas por texto recuperado; CapabilityRuntime/autorizações do domínio continuam necessários. Evitar texto de memória em system_notes, pois conversation_messages atualmente promove esse campo para role system.

## Foco, referências e contradições

Foco explícito de projeto guardado em ConversationMemory e validado a cada uso. Referência à última missão/objeto provém de ID já auditado no turno, não de palpite de LLM. Sem referência inequívoca, perguntar ao usuário em vez de executar sobre projeto errado. Projetos acessíveis são recuperáveis entre conversas, sem compartilhar histórico privado de outro proprietário.

Evidências mostram origem/revisão/data/estado. Observação vigente tem prioridade para pergunta de status. Decisão revogada pode ser mostrada como histórico, nunca como decisão vigente. Hipótese permanece hipótese. Relação contradiz inclui ambos os lados quando couber e informa conflito.

## Tempo e cancelamento

G03/G04 do spec geral regem limites. Com deadline vencido, status timeout e apenas história/fatos já obtidos; no contexto indicar memória não consultada completamente. Não alegar conhecimento do corpus inteiro. Cancelamento de voz cancela task de retrieval e fecha sessão/queries; trace marca canceled; não salvar resposta incompleta como decisão. Resposta interrompida pode conservar texto parcial na conversa com status interrupted, sem indexar automaticamente como resultado concluído.

S2 mantém streaming e FreeLLM retry já existentes, sem nova inferência. Conversa normal: uma geração. Trinity existente continua somente no caminho de planejamento atual; reduzir quatro chamadas de missão é projeto posterior condicionado à auditoria de governança.

## Persistência e cache

Knowledge ingest do turno ocorre com outbox após commit da mensagem/resultado; falha do indexador não falha resposta. Gravar ContextTrace com scope, canal, turn_id, status, fontes/revisões, epoch, duração, bytes/tokens estimados, flags de degradação, versão do builder, sem conteúdo sensível em logs.

MessageResponse pode ganhar context_trace_id e sources opcionais; frontend mostra fontes sob expansão, sem ditar todos os IDs no áudio. Não trocar contratos WebSocket na primeira integração: trace/refs podem ser ligados às mensagens persistidas e consultados via endpoint authenticated /knowledge/context-traces/{id}.

Cache de resposta: status/incidentes/ações = bypass; reuso de respostas documentais é etapa posterior: requer knowledge_epoch + retrieval_fingerprint + scope/política e auditoria dos hooks; MVP retrieval ligado sempre bypass. Voz conserva bypass. Cache desativado não impede retrieval.

## Falhas

Fonte revogada durante recuperação não é enviada; revalidar lote antes da composição. Mudanças após composição são limitação de snapshot pontual e trace registra horário; antes de qualquer ação, executor consulta autoridade/estado novo. Sem banco, a API pode estar indisponível: não prometer resposta normal sem suas dependências. Degradação de retrieval isolado permite resposta limitada, não status fictício.

## Retry e proteção de trabalho duplicado

No cliente de texto, criar request_id UUID antes de enviar e preservá-lo nos retries da mesma pergunta, inclusive resposta perdida. Campo aditivo em MessageRequest. Com retrieval ligado, exigir request_id nos novos clientes; compatibilidade de clientes antigos semcampo usa fluxo legado, sem prometer idempotência entre requests. O servidor não pode corrigir retry sem identidade estável inventando UUID a cada chamada.

Voz: request_id = UUIDv5(namespace documentado DEUS_TURN_NAMESPACE, conversation_id + ':' + session_id + ':' + turn_id). O session_id é do gateway autenticado e permanece fixo nessa sessão WebSocket; reconectar cria sessão distinta, não retoma automaticamente efeito do turno anterior. Proprietário e conversa são validados antes da derivação. Owner/epoch CAS é adquirido antes de retrieval, Trinity ou inferência; manter lease em sessão/transação própria curta. Complete compara epoch; worker morto marca failed após expiração sem rodar novamente efeito.

Enquanto retrieval ligado, bypass de cache de respostas tanto texto quanto voz até a auditoria dos hooks canônicos. metadata epoch/fingerprint permanece para rastreabilidade e futura ativação. O teste de cache da primeira versão prova bypass e invalidação de cache de retrieval; não promete reaproveitar respostas de documentos já nesta entrega.
