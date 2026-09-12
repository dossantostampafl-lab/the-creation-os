# THE CREATION OS v0.3 — Living Core

THE CREATION OS é um sistema persistente de execução governada com API FastAPI, worker operacional, frontend React, PostgreSQL e Redis. O fluxo principal conecta a interação do Criador a Inceptions, Missions, DAG de tarefas, Agents, capabilities, inferência, memória, Chronicle, projeções e dashboard operacional.

## Runtime atual

- `backend/app/api` — REST `/api/v1`, health, estado/projeções do sistema e stream autenticado de eventos.
- `backend/app/auth` — autenticação do Criador e ciclo de tokens.
- `backend/app/cognition` — contratos estruturados para avaliação cognitiva e planejamento.
- `backend/app/kernel` — distribuição, DAG, claims de tarefas, AgentExecution, supervisão, reconciliação e conclusão de Missions.
- `backend/app/capabilities` — contratos, autorização, policy, gateway e execução governada de capabilities.
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

Providers `fake` são permitidos somente em desenvolvimento/testes. Produção deve selecionar explicitamente `openai`, `freellmapi` ou `openai_compatible` e fornecer as credenciais/configurações correspondentes.

## Executar local

```bash
docker compose up --build
```

Readiness da API:

```text
GET /api/v1/health/ready
```

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

O repositório também possui CI de release, CodeQL/auditoria de dependências e um `Real Provider Gauntlet` manual para provar uma Mission com provider externo real. Esse último gate não deve ser considerado aprovado sem uma execução real bem-sucedida.

## Deploy no Render

`render.yaml` é o Blueprint canônico de produção e declara:

- `creation-api`
- `creation-worker`
- `creation-frontend`
- `creation-postgres`
- `creation-redis`

`DATABASE_URL` e `REDIS_URL` são fornecidos pelos serviços gerenciados. `APP_SECRET_KEY` é gerado pela plataforma. Credenciais reais não devem ser commitadas no Git.

O frontend usa `VITE_API_BASE_URL` para apontar para a API pública. A API executa migrations antes do Uvicorn e expõe `/api/v1/health/ready`; o worker compartilha persistência/configuração e não possui porta pública.
