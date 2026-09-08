# THE CREATION OS v0.3 — Living Core

Projeto backend do núcleo persistente do THE CREATION OS. Inclui autenticação do Criador, conversa com DEUS, Trindade, Inceptions, Central Core, Tree Core, Universos, memória, Chronicles e Pulse.

## Arquitetura

- `api` expõe REST estável `/api/v1`
- `auth` gerencia o único Criador e tokens JWT
- `chronicles` mantém histórico append-only encadeado
- `core` preserva invariantes de DEUS, SOPHIA, ROCKMAM, Central Core, Tree Core e Malkuth
- `cognition` define contratos estruturados da avaliação cognitiva
- `inference` isola ModelRouter, ProviderRegistry e InferenceProvider
- `kernel` implementa distribuição, DAG, AgentExecution e runtime operacional governado
- `memory` implementa memória de conversa, missão, universo e consciousness
- `db` e `alembic` gerenciam persistência PostgreSQL
- `redis` e `redis streams` suportam execução de tarefas

DEUS é a interface soberana com o Criador e não executa trabalho operacional. A execução percorre o kernel, Universos, Agentes, capabilities/governança e adapters autorizados.

## Requisitos

- Docker
- Docker Compose
- Python 3.12 (para execução local sem container)

## Configuração

Copie `.env.example` para `.env` e ajuste os valores.

## Executar local

```bash
docker compose up --build
```

## Migrations

```bash
docker compose exec api alembic upgrade head
```

## Criar o Criador

```bash
curl -X POST http://localhost:8000/api/v1/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"username":"creator","password":"change-me-securely"}'
```

## Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"creator","password":"change-me-securely"}'
```

## Endpoints principais

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/conversations`
- `POST /api/v1/conversations/{id}/messages`
- `GET /api/v1/inceptions`
- `POST /api/v1/inceptions/{id}/approve`
- `POST /api/v1/inceptions/{id}/reject`
- `GET /api/v1/universes` · `POST /api/v1/universes` · `POST /api/v1/universes/{id}/activate|deactivate`
- `GET /api/v1/agents?universe_id=` · `POST /api/v1/agents` · `POST /api/v1/agents/{id}/activate|deactivate`
- `GET|PUT /api/v1/memory/{conversation|mission|universe}/{scope_id}`
- `GET|POST /api/v1/memory/conscious`
- `POST /api/v1/missions/{id}/distribute`
- `POST /api/v1/missions/{id}/execute`
- `POST /api/v1/missions/{id}/manifest`
- `GET /api/v1/missions/{id}/tasks`
- `GET /api/v1/pulse`
- `GET /api/v1/chronicles?limit=100&offset=0`
- `GET /api/v1/chronicles/verify`

## Testes

Os testes de integração exigem PostgreSQL e Redis acessíveis em `localhost`.

```bash
docker compose up -d postgres redis
cd backend
pip install ".[dev]"
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/the_creation_os \
  REDIS_URL=redis://localhost:6379/0 pytest
```

Para rodar apenas os testes unitários: `pytest -m "not integration"`.
