# Brainstorm consolidado

## Intenção e premissas

O usuário quer DEUS como um Obsidian vivo: informações persistentes conectadas, acessíveis diretamente, com resposta contextual e coerente. Deseja diagnóstico do próprio OS e pediu este projeto separado para auditoria. Não pediu executar a implementação agora.

Premissas adotadas para o projeto: reutilizar PostgreSQL/Redis/Python existentes; não acrescentar APIs pagas; preservar voz local e fornecedor FreeLLM atual; diagnóstico começa observando; Obsidian começa como exportação. São decisões propostas e revisáveis na auditoria.

## Três desenhos considerados

A. PostgreSQL canônico, FTS e relações SQL, projeção Markdown. Melhor continuidade operacional e consistência; requer retrieval novo. Recomendado.
B. Vault Markdown canônico com sincronização para índices. Mais natural para edição humana; conflitos, escrita concorrente, nomes e exclusões precisam de motor próprio. Adequado somente se edição direta no Obsidian for prioridade maior que consistência inicial.
C. Grafo externo e banco vetorial, agentes conversando em cadeia. Bom para consultas especializadas em grande escala; aumenta serviços e sincronização e não resolve a falta de contexto da voz. Sem evidência de necessidade agora.

## Decisões propostas

D01. Memória central lógica, com escopo: proprietário/ACL continua obrigatório; centralizar não libera acesso universal.
D02. Fatos canônicos permanecem nas tabelas de domínio; conhecimento é projeção com origem e versão. Logs/documentos não se tornam fatos operacionais automaticamente.
D03. Retrieval textual primeiro. Vetores locais somente após benchmark com corpus em português; fake embeddings não servem.
D04. Um ContextBuilder para texto e voz. Uma geração para conversa normal; planejamento complexo mantém caminho separado. Não reescrever Trinity na primeira entrega.
D05. Nenhum LLM/embedding remoto extra na rota de montagem do contexto. Indexação e exportação em background.
D06. Eventos/outbox duráveis no PostgreSQL; Redis é aceleração. Não adicionar broker novo.
D07. Diagnóstico independente do worker de missões; detecção determinística, explicação pelo DEUS.
D08. Markdown é exportação unidirecional com IDs/revisões; sincronização bidirecional exige projeto próprio.
D09. MCPs são integrações opcionais. Download de26 servidores não implica instalar26 serviços.
D10. Rollout por flags e migrações aditivas, com dados de origem preservados.

## Objeções e respostas

“Tudo no DEUS vai deixá-lo lento?” O corpus fica na base; apenas evidências relevantes vão ao modelo. Busca local tem orçamento e cancelamento.
“Uma memória precisa de Neo4j?” Relações tipadas e consultas limitadas no PostgreSQL bastam até benchmarks indicarem insuficiência.
“DEUS pode corrigir o OS sozinho?” Observação e proposta são a primeira versão. Correção automatizada exige políticas de ação e recuperação operacional próprias.
“Sem embeddings a memória funciona?” Sim, por IDs, nomes, FTS, foco e relações. Semântica pode melhorar perguntas com pouca sobreposição lexical depois.
“Será igual ao aplicativo Obsidian?” A memória e exportação fornecem notas/links; não está previsto clonar o editor, plugins, canvas ou a interface inteira.

## Questões reservadas à auditoria

Q01: confirmar exportação inicial ou exigir edição bidirecional; esta última muda o escopo.
Q02: escolher corpus inicial e retenção após medir volume; sugerido um projeto piloto, sem importação irrestrita do disco.
Q03: confirmar modo observação do diagnóstico; autonomia de correção fica separada.
Q04: medir CPU/RAM e p95 de voz no host antes de escolher modelo de embedding.
Q05: definir compartilhamento entre proprietários se necessário. O OS atual autentica um Creator soberano; não há multitenancy pronta a ser assumida.
