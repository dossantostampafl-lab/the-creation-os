# Conselho de arquitetura — DEUS com memória central conectada

Data:2026-10-01. Base inspecionada:50924e3ca5b6f71a6a8287e2b19929da56306819, repositório the-creation-os.

Este parecer é uma proposta arquitetural, não uma implementação. Quatro agentes independentes examinaram memória, contexto/latência, diagnóstico operacional e riscos de integração. Não foram alterados código de produto, serviços, catálogo de Universos ou produção.

## Objetivo

DEUS é o interlocutor central do Creation: recupera conversas, projetos, documentos, decisões, resultados e diagnósticos relevantes, inclusive de outras conversas autorizadas, sem exigir que o usuário repita contexto nem navegue por divisões. Os agentes e Universos publicam informações diretamente na memória comum; mantêm especialidades de execução. A experiência desejada se parece com um Obsidian vivo, com fontes conectadas e histórico verificável.

## Resultado do conselho

| Especialidade | Recomendação |
|---|---|
| Dados e memória | PostgreSQL canônico; revisões e relações; Markdown como projeção |
| Contexto e voz | ContextBuilder único; uma geração para conversa; recuperação fora de cadeias hierárquicas |
| Diagnóstico operacional | Observador independente; incidentes com evidência, validade e recuperação |
| Revisão crítica | FTS primeiro; escopo antes de ranking; conteúdo recuperado fora de role system; rollout reversível |

Os quatro pareceres convergem na base PostgreSQL. A revisão crítica condiciona o rollout aos testes de isolamento, conteúdo malicioso, validade e latência; isso não equivale a afirmar que a implementação já atende esses critérios.

## Decisão recomendada

PostgreSQL existente como fonte canônica; memória transversal versionada, busca textual e relações tipadas; um ContextBuilder compartilhado por texto e voz. Redis acelera consultas/notificações, sem ser a única cópia durável. pgvector com embeddings locais entra depois, mediante avaliação. Markdown e wikilinks são exportações para Obsidian. Diagnóstico roda em processo independente das missões e publica observações/incidentes no mesmo núcleo.

Nenhum MCP, banco grafo externo, broker adicional ou nova API paga é pré-requisito. FreeLLM API continua sendo o fornecedor de geração existente; sua disponibilidade e latência não ficam garantidas por esta arquitetura.

## Evidências do código atual

- backend/app/services/deus.py: DEUS usa últimas20 mensagens da conversa e snapshot de prontidão/missões. Não recupera automaticamente as camadas de memória persistente.
- backend/app/voice_session/conversation.py: voz usa histórico e identidade compartilhada, mas não o snapshot usado pelo texto. Os canais hoje recebem informações diferentes.
- backend/app/models/entities.py: existem ConversationMemory, MissionMemory, UniverseMemory, ConsciousMemory e Chronicle. ConsciousMemory contém ARRAY(REAL), não um índice de recuperação pgvector; não possui proprietário direto, revisões/validade nem relações de conhecimento.
- backend/app/ai/embeddings.py: adapters fake, OpenAI e FreeLLMAPI; não há adapter local implementado. Fake não mede semântica e é proibido pelo builder em produção. Configuração efetiva de produção não foi inspecionada neste conselho.
- backend/app/memory/policy.py: há validação de proveniência e separação entre memória e autoridade. A listagem consciente e as APIs globais não são uma base suficiente para recuperação com múltiplos proprietários.
- backend/app/repositories/domain.py: Chronicle fornece correlação/hash/posição e lock transacional global. Não colocar amostras de áudio ou cada linha de log nesse caminho.
- backend/app/api/living_core.py e observability/probes.py: probes via Pulse são sob demanda; isso não constitui observador contínuo.
- backend/app/worker.py: refresher de projeções compartilha processo com executor de missões. O agente diagnóstico precisa sobreviver ao executor parado.

São achados estáticos, não demonstrações de exploração ou garantias de funcionamento em produção.

## Comparação de alternativas

| Alternativa | Benefício | Limitação | Parecer |
|---|---|---|---|
| PostgreSQL + busca textual + relações + vetor opcional | Reaproveita transações, infraestrutura e dados existentes | Requer modelo de conhecimento e retrieval novos | Escolhida |
| Vault Markdown como base principal | Portável, editável e amigável ao Obsidian | Concorrência, conflitos e sincronização tornam-se responsabilidade nova | Usar como exportação inicial |
| Banco grafo e banco vetorial externos | Recursos especializados para consultas grandes | Mais serviços, backups, sincronização e operação | Adiar até haver necessidade medida |
| Todo o histórico no prompt a cada pergunta | Simples como demonstração | Cresce em custo/latência, mistura contextos e supera janela do modelo | Rejeitada |
| Conselho de LLMs a cada resposta | Múltiplas perspectivas | Acrescenta chamadas sequenciais e atrasa voz | Reservar para planejamento complexo sob demanda |

## Fluxo proposto

1. Conversa, documento, decisão, execução ou diagnóstico é registrado com origem, proprietário e versão.
2. Na mesma transação, registra-se o evento de ingestão/outbox. O produtor publica diretamente, sem aguardar cadeia de divisões.
3. Worker independente consome eventos com checkpoint e idempotência; prepara projeções, relações, índices e exportação. Redis pode acordá-lo, mas o banco permite retomar após perda da notificação.
4. Ao receber uma pergunta, ContextBuilder resolve foco/projeto, consulta fatos atuais e recupera memória autorizada relevante.
5. DEUS recebe histórico recente + evidências selecionadas + estado atual e produz uma resposta normal com uma geração. Fontes são registradas junto à resposta.
6. Quando há execução, ferramentas/agentes recebem intenção validada e devolvem resultados diretamente ao núcleo. Regras de autorização e efeitos externos continuam no domínio; lembranças não conferem permissão.

A rapidez vem de preparar conhecimento em background e buscar poucos trechos pertinentes, sem chamadas extras de LLM para classificar ou resumir cada turno.

## Modelo mínimo de conhecimento

Introduzir entidades de conhecimento e revisões imutáveis, relacionadas às memórias existentes:

- Identidade estável, proprietário/escopo, tipo, projeto, título e classificação por Universo opcional.
- Revisão com conteúdo, hash, autor/processo, source_type/source_id/source_revision, observed_at, ingested_at e estado de validade.
- Tipos: documento, decisão, preferência explícita, resultado, observação diagnóstica e síntese derivada; nenhuma fala do modelo vira fato verificado automaticamente.
- Relações tipadas: pertence_a, deriva_de, depende_de, substitui e contradiz.
- Índice textual PostgreSQL para pt-BR e termos técnicos; índice vetorial opcional associado a modelo/dimensão/versão.
- Pacote contextual de cada resposta com IDs/revisões/fontes, horário do estado atual e indicação de recuperação completa/degradada.

Uma correção gera nova revisão e invalida a antiga nos índices/cache. Contradições permanecem identificáveis; uma preferência corrigida explicitamente tem precedência sobre a versão anterior. Excluir/revogar fonte deve invalidar suas projeções e impedir acesso futuro. Relações entre Universos são permitidas conforme o escopo autorizado, sem isolamento artificial por especialidade.

## Recuperação e velocidade

Primeira versão: busca por IDs/nomes, projeto ativo, decisões vigentes, busca textual, recência e expansão limitada de relações. Filtrar proprietário antes de ranking. Diferenciar ausência de informação de erro de consulta. Não executar consultas concorrentes na mesma AsyncSession.

Texto e voz usam o mesmo ContextBuilder e as mesmas regras de recuperação. O histórico recente mantém a continuidade; busca persistente fornece contexto entre conversas. Informações recuperadas são dados citáveis, não instruções system confiáveis. Não colocar texto de documentos no campo system_notes atual: esse helper gera mensagens role system. Usar bloco de evidências em papel de conteúdo suportado pelo fornecedor, acompanhado apenas por regras confiáveis no system. Delimitadores ajudam a separar conteúdo, mas a política determinística de ferramentas é que mantém a autoridade. Estado de serviço possui validade e nunca deve ser inferido exclusivamente de nota antiga.

Metas iniciais para avaliar no host: montagem/recuperação até300ms p95 e até1500–2000 tokens de memória por pergunta comum. São objetivos, não números medidos nem promessas. Medir separadamente retrieval, primeira saída de texto, TTS e primeiro áudio. Se retrieval exceder seu orçamento, cancelar trabalho pendente, usar evidências locais já disponíveis e informar degradação. Não concluir que falta de resposta da memória significa inexistência de um fato.

Conversa normal deve usar uma geração, sem sumarização/classificação remota adicional. Planejamento de missões complexo pode usar múltiplas perspectivas explicitamente. Cachear consultas por versão é útil; status vivo, permissões e ações devem evitar reaproveitar resposta semântica antiga. Reutilizar knowledge_version/retrieval_fingerprint do cache existente.

## Diagnóstico do OS

Processo separado, inicialmente observador: API, PostgreSQL, Redis, worker/heartbeat, fila/tarefas, inferência, voz, projeções e MCPs efetivamente configurados. Falha de evento não dispensa sondagens periódicas. Checagens locais determinísticas detectam; DEUS explica e correlaciona.

Observações incluem recurso, regra, resultado, latência, observed_at e TTL. Incidentes são deduplicados por escopo/recurso/regra, com aberto/reconhecido/recuperado, histerese e evidências. Causa suspeita fica separada de fato observado. Dados expirados viram stale/unknown.

Se PostgreSQL estiver fora, o diagnóstico mantém journal local limitado e importa depois com IDs idempotentes; se Redis cair, polling do registro durável continua. Se o host inteiro cair, um observador local não detecta a própria indisponibilidade: cobertura desse caso requer monitor externo, etapa opcional futura. Reiniciar ou alterar serviços automaticamente não faz parte da primeira versão; autorização de correção é política separada.

## Obsidian

Exportar Markdown com frontmatter de IDs/revisões e wikilinks. O usuário pode navegar projetos, decisões, incidentes e fontes. Começar unidirecional, evitando duas fontes da verdade. Caso edição no Obsidian seja necessária, implementar depois importação explícita com verificação de revisão/conflitos; não prometer sincronização bidirecional nesta fase.

## Sequência de implementação recomendada

1. Núcleo de conhecimento com escopo, proveniência, revisão, ingestão idempotente e busca textual; migrar/backfill somente fontes com ownership verificável.
2. ContextBuilder comum texto/voz, foco ativo, fontes por resposta e limites de tempo/contexto. Esta fase entrega o comportamento principal desejado.
3. Diagnóstico independente com incidentes e estado atual; integrar seus resultados ao ContextBuilder.
4. Exportação Markdown/Obsidian.
5. Busca híbrida com embeddings locais, apenas se benchmark demonstrar ganho de qualidade compatível com CPU/RAM e voz. Não reutilizar embeddings fake nem confundir cache semântico com memória.

Migrações aditivas, ativação gradual com flags separadas de ingestão, recuperação e exportação, e opção de voltar ao fluxo anterior. A memória persistida não deve ser apagada no rollback. Nenhuma fase exige ativar os26 MCPs baixados.

## Critérios de aceitação

- Nova conversa e nova sessão de voz recuperam decisão de projeto anterior com fonte.
- Texto e voz recebem os mesmos fatos vigentes; pronomes e pedidos de continuidade resolvem o foco correto.
- Serviço recuperado deixa de aparecer como falhando; nota antiga não prevalece sobre observação válida recente.
- Correção/exclusão de memória invalida recuperação e cache; eventos repetidos não criam duplicatas.
- Proprietário A não vê informação de B; filtro aplicado antes da busca e das relações.
- Documento com instrução maliciosa não altera identidade, permissão nem executa ação.
- Falha/reinício de indexador não perde eventos; retorno após DB/Redis indisponível preserva evidências e indica dados desatualizados.
- Conversa normal usa uma geração; registrar p95 com carga e garantir que indexação não bloqueia STT/TTS.
- Recuperação sem evidência e recuperação indisponível produzem estados diferentes.
- Exportação contém IDs estáveis, revisões e relações e não produz loops de ingestão.

## Pontos a fechar antes de implementar

Aprovar este desenho; definir se Obsidian é apenas exportação ou também editor; selecionar projetos/fontes iniciais e política de retenção; decidir autonomia de correção do diagnóstico numa etapa própria. Configuração efetiva de embeddings, limites do servidor e disponibilidade real da FreeLLM API precisam ser medidos na implantação, não assumidos.
