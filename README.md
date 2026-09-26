# THE CREATION OS v0.3 — Living Core

THE CREATION OS é um sistema persistente de execução governada com API FastAPI, worker operacional, frontend React, PostgreSQL e Redis. O fluxo principal conecta a interação do Criador a Inceptions, Missions, DAG de tarefas, Agents, capabilities, inferência, memória, Chronicle, projeções e dashboard operacional.

## Runtime atual

- `backend/app/api` — REST `/api/v1`, health, estado/projeções do sistema e stream autenticado de eventos.
- `backend/app/auth` — autenticação do Criador e ciclo de tokens.
- `backend/app/cognition` — contratos estruturados para avaliação cognitiva e planejamento.
- `backend/app/kernel` — distribuição, DAG, claims de tarefas, AgentExecution, supervisão, reconciliação e conclusão de Missions.
- `backend/app/capabilities` — contratos, autorização, policy, gateway e execução governada de capabilities, incluindo o adapter opcional e restrito do PROTO.
- `backend/app/inference` — ProviderRegistry, ModelRouter e adapters `openai`, `freellmapi` e `openai_compatible`.
- `backend/app/memory` — contratos e policy de memória governada; persistência é feita no domínio/repositórios.
- `backend/app/projections` — projeções persistidas usadas pelo dashboard e pelo estado operacional.
- `backend/app/repositories` — acesso persistente ao domínio e Chronicle append-only.
- `backend/app/worker.py` — loop operacional de reconciliação, execução, conclusão e atualização de projeções.
- `frontend` — Living Operations Terminal em React/TypeScript/Vite, alimentado pelos endpoints de estado/projeções/Chronicle/inference e SSE autenticado.

DEUS permanece como interface conceitual do Criador. Trabalho operacional é executado pelo runtime governado de Missions, Tasks, Agents e capabilities; a interface não executa capabilities diretamente.

## Requisitos

- Docker e Docker Compose
- Python 3.12 para execução local sem container
- Node.js 22 para desenvolvimento direto do frontend

## Configuração

`.env.example` na raiz é a única referência canônica de variáveis locais/de desenvolvimento. Copie-o para `.env` e ajuste os valores.

Providers `fake` são permitidos somente para bootstrap/desenvolvimento. Para inferência operacional na máquina local, selecione explicitamente `openai`, `anthropic`, `freellmapi` ou `openai_compatible` no arquivo `.env` e forneça as credenciais/configurações correspondentes.

### Providers de inferência

| `LLM_PROVIDER` | Variáveis obrigatórias | Endpoint |
| --- | --- | --- |
| `openai` | `LLM_MODEL`, `LLM_API_KEY` | `https://api.openai.com/v1/responses` |
| `anthropic` | `ANTHROPIC_MODEL`, `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1/messages` |
| `freellmapi` | `FREELLMAPI_MODEL` (ex.: `auto`), `FREELLMAPI_API_KEY` (chave `freellmapi-…` gerada pelo próprio FreeLLMAPI), `FREELLMAPI_BASE_URL` | FreeLLMAPI rodando no computador (`http://host.docker.internal:3001/v1`) |
| `openai_compatible` | `OPENAI_COMPATIBLE_MODEL`, `OPENAI_COMPATIBLE_BASE_URL` | gateway compatível (Ollama, vLLM, …) |

O provider `anthropic` usa a Messages API nativa do Claude: mensagens `system` são elevadas ao campo `system` da requisição, `ANTHROPIC_MAX_OUTPUT_TOKENS` define o teto padrão de saída (exigido pela API) e `ANTHROPIC_BASE_URL`/`ANTHROPIC_TIMEOUT_SECONDS` permitem apontar para um proxy corporativo.

#### Cadeia de fallback

`LLM_PROVIDER` é o provider primário e `LLM_FALLBACK_PROVIDERS` (lista separada por vírgula) é a ordem de reserva, usada só quando o primário falha de vez: fora do ar, inacessível, estourando o tempo, sem cota (429), com erro 5xx ou com o circuito aberto. Para FreeLLMAPI primeiro e Anthropic como reserva:

```dotenv
LLM_PROVIDER=freellmapi
LLM_FALLBACK_PROVIDERS=anthropic
FREELLMAPI_API_KEY=freellmapi-…
FREELLMAPI_MODEL=auto
ANTHROPIC_API_KEY=sk-ant-…
ANTHROPIC_MODEL=claude-sonnet-4-5
```

Enquanto o FreeLLMAPI responde, nenhuma chamada vai para a Anthropic — nem do DEUS, nem da Trinity, nem do worker. Depois de 3 falhas seguidas o FreeLLMAPI fica 30 segundos fora da rota (circuit breaker), valendo para todas as requisições, e então volta a ser tentado primeiro. Uma chave recusada (401/403) não aciona a reserva: é erro de configuração e aparece como erro.

Todos os providers da cadeia precisam estar completamente configurados: se faltar credencial ou modelo de um deles, o boot da inferência falha explicitamente em vez de silenciar a reserva. O primário responde com o modelo configurado e cada reserva com o seu próprio modelo padrão; o `provider`/`model` efetivamente usados são registrados na mensagem e no Chronicle. `fake` não é aceito como fallback.

Enquanto o provider selecionado for `fake`, o status de inferência é reportado como `UNCONFIGURED` e o Creator Console permanece desabilitado — o sistema recusa fabricar respostas do DEUS.

### Voz do DEUS (como uma Alexa)

Na barra de conversa, o botão de orelha liga a palavra de ativação: diga **"Deus"** e ele responde "Estou aqui" e ouve o seu pedido. Também dá para falar tudo de uma vez: "Deus, como estão os universos?". Depois da primeira fala a conversa continua: quando o DEUS termina de responder ele volta a ouvir sozinho, sem precisar dizer "Deus" de novo. A conversa termina depois de alguns segundos de silêncio ou quando você diz "tchau", "obrigado", "pode parar" ou "é só isso". O botão de microfone faz a mesma coisa sem a palavra de ativação, e o de alto-falante liga ou desliga a voz.

- **Voz ElevenLabs (recomendada):** no `.env`, defina `ELEVENLABS_ENABLED=true`, `ELEVENLABS_API_KEY=<sua chave>` e, se quiser, outro `ELEVENLABS_VOICE_ID`. A chave fica só no backend (`POST /api/v1/voice/synthesize`).
- **Sem ElevenLabs:** o DEUS usa a voz do próprio navegador, automaticamente.
- **Microfone:** use Chrome ou Edge. Os navegadores só liberam o microfone em `https://` ou em `http://localhost`, então abra `http://localhost:8080` no próprio computador (pelo IP da rede local, o microfone fica bloqueado).

### Trinity: SOPHIA e ROCKMAM

Cada mensagem ao DEUS passa antes pela **SOPHIA**, que entende a intenção: conversa, pergunta, pedido de missão, decisão ou comando. Quando você pede para algo ser criado ou realizado ("Deus, cria uma landing page para o produto"), a Trinity delibera:

1. **SOPHIA** avalia oportunidades, riscos e recomenda o que fazer.
2. **ROCKMAM** transforma isso em objetivo, restrições e um plano de missão em etapas, cada uma num Universo.
3. A **guarda do ROCKMAM** decide a viabilidade sem depender do modelo: o plano é viável só se cada Universo dele existe, está ativo e tem um Agent ativo.

- **Viável:** o ROCKMAM já entrega a Missão pronta. A Inception é aprovada (o pedido foi seu), a Missão é criada, planejada e validada, e **fica aguardando só a sua autorização**. Diga **"autoriza"** ou **"pode iniciar"** e ela é autorizada, distribuída aos Agents e entra em execução (`POST /api/v1/missions/{id}/start`). Diga **"cancela"** para descartar. No chat, o cartão "MISSION READY" tem os botões **Authorize & start** e **Cancel**.
- **Ainda não viável:** nada é preparado. O cartão "NOT VIABLE YET" diz o que falta (por exemplo, "Universe web is not active") e o DEUS explica o que você precisa configurar.

Nada entra em execução sem a sua autorização. Tudo fica no Chronicle: `sophia_intent_perceived`, `inception_created`, `inception_submitted`, `inception_approved`, `mission_created`, `mission_planned`, `mission_validated` e, na autorização, `mission_authorized`, `mission_distributed` e `mission_execution_started`. Se o modelo falhar, fica `trinity_failed` e o DEUS responde normalmente.

- **Custo:** a percepção é uma chamada curta por mensagem. A deliberação soma duas chamadas, só nos pedidos de missão. Essas chamadas não passam pelo Semantic Cache.
- **Configuração:** `TRINITY_ENABLED=false` desliga a Trinity. `TRINITY_MIN_CONFIDENCE` (padrão `0.7`) é a confiança mínima da SOPHIA para deliberar.

### Limites de segurança

- **Bootstrap**: `POST /auth/bootstrap` só aceita as credenciais configuradas em
  `CREATOR_BOOTSTRAP_USERNAME`/`CREATOR_BOOTSTRAP_PASSWORD`, em qualquer ambiente. Antes o
  bloqueio valia só em produção, então qualquer um que chegasse primeiro reclamava a conta
  soberana de uma instalação de desenvolvimento exposta na rede.
- **Chave de assinatura**: em produção `APP_SECRET_KEY` precisa ter 32 caracteres ou mais e não
  pode ser o valor publicado no `.env.example`; o mesmo vale para `CREATOR_BOOTSTRAP_PASSWORD`.
- **Trocar a senha do Criador**: edite `CREATOR_BOOTSTRAP_PASSWORD` no `.env`, recrie a API
  (`up -d --force-recreate api worker`) e rode `rotate-creator-password` dentro do contêiner da
  API. Ele recusa se o `.env` não mudou, encerra todas as sessões abertas sob a senha antiga e
  registra `creator_password_rotated` no Chronicle.
- **Sessão**: um Creator desativado não passa mais em `/auth/me`, `/auth/refresh` nem
  `/auth/logout` — o refresh token deixa de girar no momento da desativação.
- **Efeito externo é declarado pelo adapter**, não pelo pedido do modelo: `external_effect` e a
  classe mínima de idempotência vêm do código do adapter, então um modelo que escreve
  `"external_effect": false` não transforma uma capability que alcança o mundo em uma que não
  alcança. Um adapter que não declara nada é tratado como o pior caso.
- **Escopo fecha, nunca abre**: uma entrada de `scope` que não pode ser lida como lista nega o
  pedido em vez de virar "sem restrição", e uma Mission restrita a recursos nomeados recusa um
  pedido sem recurso.
- **Chave de provedor nunca em claro**: um `*_BASE_URL` com `http://` só é aceito para esta
  máquina, um container ou a rede privada; para um host público é exigido `https`, e a URL não
  pode carregar credenciais nem query string.
- **Servidor na nuvem**: `docker-compose.cloud.yml` sobe a pilha com sistema de arquivos
  somente-leitura, `no-new-privileges` e o banco e o Redis em uma rede interna sem rota para
  fora; o `install.sh` gera a senha do Postgres na primeira instalação.

### O que um Agent pode fazer: capabilities

Um Agent nunca executa nada por conta própria. Ele pede, através do mecanismo de tools do modelo
(`capability_intent`), e a policy do gateway decide a partir da autorização da Mission: sem a
capability na lista de permitidas, o pedido é negado e registrado em `CapabilityInvocation`.

- **`workspace`** (`write`, `read`, `list`, `append`) — arquivos de trabalho. Cada Mission tem o seu
  próprio diretório dentro de `WORKSPACE_ROOT` e não alcança nada fora dele: caminhos absolutos,
  `..`, separadores do Windows e symlinks que saiam do diretório são recusados. `WORKSPACE_MAX_BYTES`
  limita o tamanho de cada arquivo. No Docker o diretório é o volume `workspace_data`.
- **`web`** (`fetch`) — leitura de páginas públicas. Só `http` e `https`; cada endereço é resolvido e
  recusado se não estiver na internet pública (loopback, redes privadas, o serviço de metadados da
  nuvem). Redirects são seguidos manualmente e cada salto é verificado de novo, no máximo três.
  O Criador pode restringir a Mission a hosts nomeados com `scope.web_allowed_hosts`.
  `WEB_CAPABILITY_ENABLED=false` desliga a capability; `WEB_TIMEOUT_SECONDS` e `WEB_MAX_BYTES`
  controlam o timeout e o tamanho lido.

Nenhuma das duas tem efeito externo (`external_effect`), portanto nenhuma precisa de
`external_effects_allowed` na autorização — mas ambas continuam sujeitas à lista de capabilities
permitidas, ao escopo de ações e recursos, e à expiração da autorização.

### Bridge seguro com o PROTO

O worker pode registrar a capability `proto` para enviar Missions apenas ao bridge autenticado `/creation/missions` do PROTO. A integração é habilitada somente quando `PROTO_BASE_URL` e `PROTO_CREATION_SHARED_SECRET` estão configurados; `PROTO_TIMEOUT_SECONDS` controla o timeout de transporte.

O host do PROTO é configuração fixa do processo: Agents e `CapabilityIntent` não podem fornecer URL, token ou headers. Quando o PROTO estiver na mesma máquina, use `host.docker.internal`; em outra máquina da LAN, use o IP privado correspondente. O adapter local aceita somente os jobs `market-data-health`, `opportunity-scan` e `shadow-decision`, nos modos `LIVE_MONITORING`, `SIMULATION`, `PAPER_TRADING` ou `HISTORICAL_REPLAY`.

Este bridge não expõe execução financeira. Respostas do PROTO são rejeitadas se indicarem `financial_connectivity=true` ou `real_money_execution=true`. O shared secret é usado somente no header `X-Proto-Creation-Token` e não deve ser persistido em `CapabilityInvocation`, Chronicle ou logs.

## Execução local canônica

O runtime suportado do THE CREATION OS é Docker Compose na máquina local. A topologia é:

- `frontend` — exposto à rede local em `0.0.0.0:8080`;
- `api` — publicado somente em `127.0.0.1:8000` para diagnóstico local;
- `worker` — sem porta pública;
- `postgres` — privado na rede Docker, com volume persistente;
- `redis` — privado na rede Docker, com volume persistente.

No Windows/PowerShell:

```powershell
.\scripts\local-start.ps1
```

O script cria `.env` a partir de `.env.example` quando necessário, gera segredos locais, sobe o stack, aguarda os health checks e mostra o endereço LAN.

Status:

```powershell
.\scripts\local-status.ps1
```

Parar preservando os dados:

```powershell
.\scripts\local-stop.ps1
```

Apagar também os volumes locais do PostgreSQL/Redis:

```powershell
.\scripts\local-stop.ps1 -PurgeData
```

Também é possível operar diretamente:

```bash
docker compose up -d --build
docker compose ps
```

Health checks:

```text
http://127.0.0.1:8000/api/v1/health/ready
http://127.0.0.1:8080/healthz
http://127.0.0.1:8080/api/v1/health/ready
```

Para outro dispositivo da mesma rede, abra `http://<IP-LAN-DO-COMPUTADOR>:8080`. Se o Windows Defender Firewall bloquear a conexão, libere somente a porta TCP 8080 para o perfil de rede privada.

## Colocar online (grátis)

Para publicar na internet com HTTPS, sem pagar hospedagem, use uma máquina *Always Free* da Oracle Cloud. O passo a passo está em [`deploy/oracle/README.md`](deploy/oracle/README.md), e um único script instala e sobe tudo: `sudo ./deploy/oracle/install.sh`. Ele usa o `docker-compose.cloud.yml`, que põe o Caddy com HTTPS automático nas portas 80 e 443 e não expõe mais nada.

## Ambiente de desenvolvimento online (Codespaces)

Além da execução local canônica, o repositório traz um dev container (`.devcontainer/`) que reaproveita o mesmo `docker-compose.yml`. É um caminho adicional para desenvolvimento, não um substituto da topologia local.

Como abrir: no GitHub, "Code" > "Codespaces" > "Create codespace on main". Também funciona localmente em VS Code com "Dev Containers: Reopen in Container".

O dev container sobe a stack completa (`api`, `frontend`, `worker`, `postgres`, `redis`), cria `.env` a partir de `.env.example` quando ainda não existe e anexa o VS Code ao container `api` (Python 3.12), com o repositório montado em `/workspace`.

Acesse a porta encaminhada **8080** ("Frontend (UI + API proxy)"): o nginx serve a UI e faz proxy de `/api/` para a `api`, de modo que UI e API ficam no mesmo origin. A porta 8000 é encaminhada apenas para acesso direto à API (`/api/v1/health/ready`).

As migrations continuam sendo aplicadas pelo `command` do serviço `api` no boot do stack.

Ao abrir, `.devcontainer/prepare-env.sh` deixa o `.env` pronto, e pode ser rodado de novo a qualquer momento sem estragar nada:

- cria o `.env` a partir do `.env.example` quando ele não existe;
- **acrescenta as configurações que o `.env.example` ganhou depois**, preservando tudo o que você já preencheu. Um `.env` antigo é o motivo mais comum de uma chave parecer configurada e o provider não responder: a variável que ele precisa simplesmente não está no arquivo;
- **preenche os segredos em branco a partir do ambiente**, então um Codespace secret basta e a chave nunca precisa ser colada no editor — o que o navegador bloqueia em tablet e celular;
- se uma chave chegou e o `LLM_PROVIDER` ainda era `fake`, aponta para o provider correspondente.

Ele nunca sobrescreve um valor já preenchido e nunca imprime um segredo.

Para usar Codespace secrets, cadastre em **github.com/settings/codespaces** os nomes que quiser (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `FREELLMAPI_API_KEY`, `ELEVENLABS_API_KEY`, entre outros), dando acesso a este repositório, e recrie o Codespace.

Em host Windows, crie o `.env` antes de abrir o dev container (`.\scripts\local-start.ps1` já faz isso, ou copie `.env.example` manualmente): a criação automática do `.env` depende de um shell POSIX no host.

## Migrations

```bash
docker compose exec api alembic upgrade head
```

Veja `backend/MIGRATIONS.md` para a nota de compatibilidade histórica relevante ao schema de embeddings.

## Autenticação inicial

Bootstrap do Criador:

```bash
curl -X POST http://localhost:8000/api/v1/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"username":"creator","password":"change-me-securely"}'
```

Login:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"creator","password":"change-me-securely"}'
```

## Universos e Agents iniciais

Com o banco vazio não existe Universo nem Agent, e o ROCKMAM devolve toda Missão como "não viável": um plano só é viável quando cada Universo dele está ativo e tem um Agent ativo. Depois de criar o Criador, rode uma vez:

```bash
docker compose exec api seed-universes
```

Isso cria e ativa `engineering`, `content`, `research` e `operations`, cada um com um Agent ativo que usa o `LLM_PROVIDER` configurado. O comando pode ser repetido à vontade: ele só preenche o que falta e reativa o que foi desligado, sem duplicar nada. Tudo fica no Chronicle.

Esses são só um ponto de partida. Crie, renomeie ou desative os seus pelos endpoints `/api/v1/universes/*` e `/api/v1/agents/*` assim que souber quais domínios você realmente usa.

## Superfície operacional

Principais grupos de endpoints:

- autenticação: `/api/v1/auth/*`
- conversations/messages: `/api/v1/conversations/*`
- Inceptions: `/api/v1/inceptions/*`
- Missions e Tasks: `/api/v1/missions/*`
- Universes e Agents: `/api/v1/universes/*`, `/api/v1/agents/*`
- memória: `/api/v1/memory/*`
- Chronicle/Pulse: `/api/v1/chronicles*`, `/api/v1/pulse`
- estado/projeções/eventos: `/api/v1/system/state`, `/api/v1/system/projections`, `/api/v1/system/events`
- inference health/telemetry: `/api/v1/system/inference`

O dashboard consome estado/projeções persistidos e Chronicle/SSE. Indicadores operacionais não devem ser hardcoded no frontend.

## Testes

A suíte completa de backend usa PostgreSQL e Redis:

```bash
cd backend
pip install ".[dev]"
ruff check .
mypy app
python -m alembic upgrade head
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

O repositório também possui CI de build do runtime local, CodeQL/auditoria de dependências e um `Real Provider Gauntlet` manual para provar uma Mission com provider externo real. Esse último gate não deve ser considerado aprovado sem uma execução real bem-sucedida.

## Modelo de implantação

O THE CREATION OS suporta dois modos de execução, ambos mantidos e validados no CI:

### (a) Local / LAN via Docker Compose

Topologia canônica para uso em estação de trabalho ou rede local. Somente o frontend é publicado na LAN (`8080`); API, PostgreSQL e Redis permanecem restritos ao host ou à rede Docker.

```bash
cp .env.example .env
docker compose up -d --build
curl --fail http://localhost:8000/api/v1/health/ready
curl --fail http://localhost:8080/healthz
curl --fail http://localhost:8080/api/v1/health/ready
```

Para um perfil endurecido (containers read-only, rede interna para dados, segredos obrigatórios via variáveis de ambiente) use `docker-compose.prod.yml`:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### (b) Cloud via Render

`render.yaml` é um blueprint Render que descreve `creation-api` (web), `creation-worker` (worker), `creation-frontend` (web, build por `frontend/Dockerfile.render` e servido por `frontend/nginx.render.conf` na porta `10000`), `creation-redis` (keyvalue) e o banco gerenciado `creation-postgres`. Migrações rodam no `preDeployCommand`; `DATABASE_URL` e `REDIS_URL` vêm de referências gerenciadas, e segredos/providers são `sync: false` (informados no painel). Não há defaults `fake` de provider nesse modo.

Nenhum dos modos é publicado automaticamente em merge para `main`: o GitHub continua sendo usado apenas para versionamento, Pull Requests, CI, CodeQL e auditoria de dependências.
