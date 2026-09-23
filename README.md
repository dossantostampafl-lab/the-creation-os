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

Enquanto o provider selecionado for `fake`, o status de inferência é reportado como `UNCONFIGURED` e o Creator Console permanece desabilitado — o sistema recusa fabricar respostas do DEUS.

### Voz do DEUS (como uma Alexa)

Na barra de conversa, o botão de orelha liga a palavra de ativação: diga **"Deus"** e ele responde "Estou aqui" e ouve o seu pedido. Também dá para falar tudo de uma vez: "Deus, como estão os universos?". Depois da primeira fala a conversa continua: quando o DEUS termina de responder ele volta a ouvir sozinho, sem precisar dizer "Deus" de novo. A conversa termina depois de alguns segundos de silêncio ou quando você diz "tchau", "obrigado", "pode parar" ou "é só isso". O botão de microfone faz a mesma coisa sem a palavra de ativação, e o de alto-falante liga ou desliga a voz.

- **Voz ElevenLabs (recomendada):** no `.env`, defina `ELEVENLABS_ENABLED=true`, `ELEVENLABS_API_KEY=<sua chave>` e, se quiser, outro `ELEVENLABS_VOICE_ID`. A chave fica só no backend (`POST /api/v1/voice/synthesize`).
- **Sem ElevenLabs:** o DEUS usa a voz do próprio navegador, automaticamente.
- **Microfone:** use Chrome ou Edge. Os navegadores só liberam o microfone em `https://` ou em `http://localhost`, então abra `http://localhost:8080` no próprio computador (pelo IP da rede local, o microfone fica bloqueado).

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

## Ambiente de desenvolvimento online (Codespaces)

Além da execução local canônica, o repositório traz um dev container (`.devcontainer/`) que reaproveita o mesmo `docker-compose.yml`. É um caminho adicional para desenvolvimento, não um substituto da topologia local.

Como abrir: no GitHub, "Code" > "Codespaces" > "Create codespace on main". Também funciona localmente em VS Code com "Dev Containers: Reopen in Container".

O dev container sobe a stack completa (`api`, `frontend`, `worker`, `postgres`, `redis`), cria `.env` a partir de `.env.example` quando ainda não existe e anexa o VS Code ao container `api` (Python 3.12), com o repositório montado em `/workspace`.

Acesse a porta encaminhada **8080** ("Frontend (UI + API proxy)"): o nginx serve a UI e faz proxy de `/api/` para a `api`, de modo que UI e API ficam no mesmo origin. A porta 8000 é encaminhada apenas para acesso direto à API (`/api/v1/health/ready`).

As migrations continuam sendo aplicadas pelo `command` do serviço `api` no boot do stack.

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

O THE CREATION OS não depende de Railway, Render ou outro runtime cloud. O Docker Compose local é a topologia canônica. O repositório não contém gatilho de deploy cloud; persistência operacional fica nos volumes Docker locais.

O GitHub continua sendo usado para versionamento, Pull Requests, CI, CodeQL e auditoria de dependências. Merge em `main` não deve publicar automaticamente a aplicação em nenhum provedor externo.
