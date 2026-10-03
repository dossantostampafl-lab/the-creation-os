# Creation OS conectado — operação e arquitetura

O PostgreSQL guarda a memória canônica de Deus. Texto e voz usam o mesmo contexto, com foco opcional por projeto, histórico validado, estado atual e até seis evidências. O Obsidian recebe uma exportação; editar Markdown não altera o banco.

## Componentes entregues

| Componente | Comportamento |
|---|---|
| Voz | Vosk pt-BR reconhece áudio no servidor; Kokoro `pm_santa` sintetiza a voz masculina local. Wake word «Deus», conversação contínua, interrupção e telemetria. Nenhum SDK de síntese paga. |
| Resposta | FreeLLMAPI é o caminho principal configurável existente. Voz tenta novamente uma falha antes do primeiro texto. Latência depende de rede/modelo/CPU; não há garantia de resposta em menos de um segundo. |
| Memória | Revisões imutáveis, escopo do Creator, projetos, dependências, relações, revogação transitiva e PostgreSQL FTS em português. Não confirma uma afirmação do modelo como resultado executado. |
| Contexto | Consulta com prazo300ms; rastreio com prazo100ms. Falhas são explícitas; conteúdo recuperado fica fora das instruções de sistema. Resposta derivada mantém dependências; histórico sem proveniência validável é descartado. |
| Idempotência | UUID de requisição no texto e UUIDv5 de sessão/turno na voz. Repetição concluída retorna a mesma resposta; requisição em andamento retorna409. Lease120s, renovação20s e conclusão na mesma transação dos efeitos. |
| Observador | Processo independente observa DB/Redis/API, heartbeats de workers, fila e espaço no volume. Três falhas abrem incidente, duas recuperações encerram; observações expiram45s. Não reinicia serviços ou executa correções; recebe somente conexãoDB/Redis e flags, sem segredos de autenticação/LLM de produção. |
| Autonomia | Os12 universos ativos com agentes pesquisam sinais na memória autorizada a cada60s. Oportunidades referenciam item/revisão, são hipóteses e não criam missões automaticamente. Não representa pesquisa irrestrita na internet ou lucro demonstrado. |
| Obsidian | Exportação30s, diárioSQLite, arquivo temporário exclusivo, troca atômica, recuperação após crash. Arquivos humanos conflitantes são preservados; revogados vão para quarentena privada. |
| Cyber Range | Controller, Juice Shop, WebGoat/WebWolf isolados; catálogo, ativação, reset, snapshots, restauração e evidências. Dashboard usa controlador/relay configurado; ausência do laboratório aparece explicitamente. |
| Móvel | Projetos Capacitor Android/iOS, permissão de microfone, HTTPS, haptics e encerramento da captura quando o app vai ao fundo. Não mantém wake word no background. |

## Ativação

Faça backup antes de habilitar o contexto. No servidor Oracle já instalado, execute `sudo ./deploy/oracle/enable-connected-deus.sh` ou a tarefa `enable-connected-deus` do workflowDeploy. O script guarda backup privado do DB/.env, sobe workers do perfil `connected-deus`, espera readiness e importa somente mensagens do Creator. Falha de readiness restaura flags, sem remover dados ou aplicar downgrade. Mantenha os backups fora dos pacotes e da internet.

Em instalação nova:

```sh
cp .env.example .env
# Configure banco, autenticação e o gateway LLM conforme README/OPERACAO.
# Defina as cinco flags DEUS_*_ENABLED do subsistema conectado como true.
docker compose --profile connected-deus up -d --build
docker compose exec api seed-universes
docker compose exec api python -m app.voice_session.prepare
docker compose exec api python -m app.knowledge.backfill --apply
```

O bootstrap de autenticação e os modelos devem estar preparados antes do uso. Preserve `SOVEREIGN_CREATOR_ID`; com mais de um Creator ativo e sem soberano configurado, diagnóstico/exportação/descoberta não escolhem um proprietário por conta própria. Voice session precisa de `DEUS_VOICE_SESSION_ENABLED=true` e inference real configurada; `fake` é apenas para testes.

Para aplicações nativas, acrescente `https://localhost,capacitor://localhost` à lista CORS permitida, preservando origens existentes. O script de ativação faz essa alteração. Nunca use wildcard com credenciais.

## API e interface

Na gavetaVitals estão pesquisa, inclusão/revogação de memória, projetos e foco da conversa atual; também está o controle do laboratório. Todas as rotas abaixo requerem token do Creator soberano.

- `POST/GET /api/v1/knowledge/projects`: criar/listar projetos.
- `POST /knowledge/items`: Candidate e UUID `request_id`; revisão exige `expected_revision_id`.
- `POST /knowledge/search`: `query` e `project_id` opcional. Até seis evidências e um salto de relações, sempre filtrados por proprietário/projeto antes do ranking.
- `PUT/GET /knowledge/conversations/{uuid}/focus`: `project_id` ou null. O foco usa a memória de conversa existente e vale para texto/voz.
- `DELETE /knowledge/items/{uuid}?expected_revision_id=...`: tombstone e invalidação de derivados, sem apagar o histórico de auditoria.
- `GET /knowledge/context-traces/{uuid}`: referências e prazo da consulta, limitado ao proprietário.
- `GET /cyber-range/status`, `POST /cyber-range/start` com `scenario_id`, `POST /cyber-range/reset`, `POST/GET /cyber-range/snapshots`.

A consulta global preserva todos os projetos do mesmo Creator; foco restringe a recuperação por projeto. O histórico de respostas com foco diferente não entra no novo contexto; mensagens legadas sem proveniência não são promovidas. Revogação remove fontes/derivados da recuperação e exportação, mas não é apagamento físico de dados pessoais. O operador deve executar sua política de eliminação e de backups quando solicitada.

## Cyber Range sem conectar alvos à produção

```sh
docker compose -f cyber_range/compose.yml --profile cyber-range up -d --build
bash cyber_range/scripts/verify.sh
```

Portas de host: Controller7070, Juice Shop3000, WebGoat18080, WebWolf9090, todas em127.0.0.1. WebGoat usa8080 somente dentro de sua rede;18080 elimina o conflito com a interface do OS.

API executada no próprio host pode usar `CYBER_RANGE_CONTROLLER_URL=http://127.0.0.1:7070`. Para API em Docker, use o relay privado:

1. Obtenha o IPgateway privado da rede do API com `docker network inspect`.
2. Gere um segredo aleatório de32+ caracteres e grave `CYBER_RANGE_CONTROL_TOKEN` no `.env` privado do API e no ambiente do relay, sem imprimir o segredo.
3. No host, rode `python3 cyber_range/control_relay.py --bind <IPgateway-privado>`; use um serviço supervisionado com esse mesmo usuário, sem privilégios e sem Docker socket.
4. Configure `CYBER_RANGE_CONTROLLER_URL=http://host.docker.internal:7071` no API e recrie o serviço.

O relay aceita apenas lifecycle/catalog/state/snapshots com autenticação e caminhos fixos. Não encaminha URLs arbitrárias, tráfego dos alvos ou corpos de requisição. Não exponha7071 em IPpúblico, não conecte `range_targets` a `tco_net` e não coloque segredos de produção dentro do laboratório. Para restauração/evidência detalhada, use o Controller loopback e o runbookexistente.

## Rollback e limites

Desative as flags, pare `knowledge-worker`, `diagnostics-worker`, `discovery-worker`, e recrie API/worker. As revisões canônicas permanecem. Não faça downgrade de banco com dados de memória sem um procedimento de backup/restauração validado.

FTS e os limites atuais são para um corpus inicial; há limite256KiB por fonte, dependências32/profundidade8, candidatos30, seis evidências e2000tokens estimados porbytes. IndexaçãoFTS é transacional; receipts servem às projeções. Observações confirmadas do diário têm retenção7dias; pendentes nunca são descartadas silenciosamente, e o diário sinaliza lotação em100MiB. O observador não sobrevive à queda do próprio host.

Os MCPs já baixados são pacotes opcionais em `creation-mcps-*.zip`, com instalação/autorização própria. Não foram ativados indiscriminadamente, nem usados para negociar dinheiro ou conceder shell. A arquitetura auditada preservada está em `docs/architecture/deus-memory-project`; decisões concretas da implementação prevalecem nesta documentação operacional.
